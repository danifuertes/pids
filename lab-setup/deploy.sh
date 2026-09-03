#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Regenerate the week 3 (RoboMaster) workspace on the lab computers.
#
# Run it ON THE MASTER NODE, from a clone of this repository:
#
#     lab-setup/deploy.sh                    # every node in nodes.yaml
#     lab-setup/deploy.sh 192.0.2.10       # only these nodes
#     lab-setup/deploy.sh --dry-run          # show what it would do, change nothing
#
# For every node it:
#   1. DELETES /home/<user>/robomaster        <- last course's edits are lost
#   2. copies src/pids/week3/  -> /home/<user>/robomaster/week3
#   3. installs the python environment with pixi, inside week3/
#   4. copies labelimg/labelimg.sh -> /home/<user>/robomaster/labeling/
#
# The result is a flat folder the students can just open; the src/pids/ layout
# of this repository is not reproduced there.
#
#     /home/<user>/robomaster/
#         week3/                    the folder the students open in VS Code
#             *.py, audio/, ...     the code they edit
#             pyproject.toml        the environment  (run "pixi shell" here)
#             pixi.lock
#             .pixi/                built by pixi on the node, not copied
#             .vscode/settings.json points the debugger at .pixi, hides the rest
#         models/                   where their week 2 checkpoint goes
#         labeling/labelimg.sh
#
# The environment sits inside week3/ because that is the folder the students
# open: the VS Code python extension only looks for .pixi/envs/ inside the
# workspace folder, so an environment one level up is not picked up and the
# debugger silently falls back to the system python.
#
# The environment is the repository's own pyproject.toml, with the editable
# install of the "pids" package removed on the fly: that dependency needs
# src/pids/, which is deliberately not deployed. There is no second dependency
# list to keep in sync -- edit pyproject.toml and re-run this script.
#
# Installing the environment is the slow part, so when one is already present
# the script asks whether to rebuild it (--force-env answers yes in advance).
#
# Connection details (hosts, user, password) come from lab-setup/nodes.yaml.
# A node that is switched off is reported at the end; it does not stop the run.
# ---------------------------------------------------------------------------

set -uo pipefail   # no -e on purpose: one unreachable node must not abort

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

CONFIG_FILE="${CONFIG_FILE:-$SCRIPT_DIR/nodes.yaml}"
DEST_NAME="robomaster"
WEEK3_SRC="$REPO_DIR/src/pids/week3"
LABELIMG_SRC="$REPO_DIR/labelimg/labelimg.sh"
PYPROJECT_SRC="$REPO_DIR/pyproject.toml"
MANIFEST_DIR=""                     # staging dir, filled in by prepare_manifest
MANIFEST_FILES=(pyproject.toml)     # pixi.lock is added when one is generated

ASSUME_YES=0
DRY_RUN=0
FORCE_ENV=0
FILTER=()

SSH_OPTS=(
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile=/dev/null
    -o LogLevel=ERROR
    -o ConnectTimeout=10
)

# Never copied to a student machine
TAR_EXCLUDES=(
    '--exclude=__pycache__'
    '--exclude=.ipynb_checkpoints'
    '--exclude=*.pyc'
    '--exclude=serial_number.txt'   # written by connect.py, robot-specific
    '--exclude=predictions'         # output of plot_predictions()
    '--exclude=.pixi'               # an environment belongs to a node, not here
    '--exclude=.vscode'             # written below, per node
)

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

if [[ -t 1 ]]; then
    RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'
    BOLD=$'\033[1m';   RESET=$'\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BOLD=''; RESET=''
fi

info() { echo "    $*"; }
ok()   { echo "${GREEN}[ ok ]${RESET} $*"; }
warn() { echo "${YELLOW}[warn]${RESET} $*" >&2; }
err()  { echo "${RED}[fail]${RESET} $*" >&2; }
die()  { err "$*"; exit 1; }

usage() {
    cat <<EOF
Usage: ${0##*/} [options] [host ...]

Regenerates /home/<user>/$DEST_NAME on the lab computers listed in
${CONFIG_FILE#"$REPO_DIR"/}: the old folder is deleted and week3/ (with its pixi
environment inside), models/ and labeling/ are created again.

With no hosts, every node in the config is deployed.

Options:
  -y, --yes           do not ask for confirmation. An environment that is
                      already installed is kept (add --force-env to rebuild it)
  -f, --force-env     always rebuild the pixi environment, without asking
  -n, --dry-run       print what would be done, change nothing
  -c, --config FILE   use another config file (default: lab-setup/nodes.yaml)
  -h, --help          show this help
EOF
}

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case $1 in
        -y|--yes)       ASSUME_YES=1 ;;
        -f|--force-env) FORCE_ENV=1 ;;
        -n|--dry-run)   DRY_RUN=1 ;;
        -c|--config)    [[ $# -ge 2 ]] || die "--config needs a file"
                        CONFIG_FILE=$2; shift ;;
        -h|--help)      usage; exit 0 ;;
        -*)             die "unknown option: $1 (try --help)" ;;
        *)              FILTER+=("$1") ;;
    esac
    shift
done

[[ -d $WEEK3_SRC     ]] || die "source folder not found: $WEEK3_SRC"
[[ -f $LABELIMG_SRC  ]] || die "file not found: $LABELIMG_SRC"
[[ -f $PYPROJECT_SRC ]] || die "file not found: $PYPROJECT_SRC"

if [[ ! -f $CONFIG_FILE ]]; then
    err "config file not found: $CONFIG_FILE"
    echo "      Create it with:  cp $SCRIPT_DIR/nodes.example.yaml $CONFIG_FILE" >&2
    echo "      then edit it with the hosts, user and password of the nodes." >&2
    exit 1
fi

# The config holds passwords: warn if anybody else on the master can read it
config_perms=$(stat -c '%a' "$CONFIG_FILE" 2>/dev/null || echo '')
if [[ -n $config_perms && ${config_perms: -2} != "00" ]]; then
    warn "${CONFIG_FILE##*/} is readable by other users (mode $config_perms). Run: chmod 600 $CONFIG_FILE"
fi

# ---------------------------------------------------------------------------
# Config parsing
#
# "nodes" is a plain list of hosts (an IP address or a DNS name); the account
# to log in with comes from "defaults". Emits one tab-separated
# "host<TAB>user<TAB>password" record per node. Supports the subset of YAML
# documented in nodes.example.yaml.
# ---------------------------------------------------------------------------

parse_nodes() {
    awk '
        function trim(s)    { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
        function unquote(s) { if (s ~ /^".*"$/) s = substr(s, 2, length(s) - 2); return s }
        function indent(s)  { match(s, /^ */); return RLENGTH }

        # A bare value. An inline # comment is only stripped from unquoted
        # values, so a password can contain a quoted "#".
        function scalar(s,   v) {
            v = trim(s)
            if (v !~ /^"/) { sub(/[ \t]+#.*/, "", v); v = trim(v) }
            return unquote(v)
        }

        # Everything after the first ":"
        function val(line) { return scalar(substr(line, index(line, ":") + 1)) }

        /^[ \t]*$/ { next }
        /^[ \t]*#/ { next }

        # Top-level key: starts a new section
        indent($0) == 0 && /^[A-Za-z_][A-Za-z0-9_]*:/ {
            section = $0; sub(/:.*/, "", section)
            next
        }

        section == "defaults" {
            if      ($0 ~ /^[ \t]*user:/)     def_user = val($0)
            else if ($0 ~ /^[ \t]*password:/) def_pass = val($0)
            next
        }

        section == "nodes" {
            if ($0 ~ /^[ \t]*-/) {
                line = $0
                sub(/^[ \t]*-[ \t]*/, "", line)
                line = scalar(line)
                if (line != "") hosts[++n] = line
            }
            next
        }

        END {
            for (i = 1; i <= n; i++)
                printf "%s\t%s\t%s\n", hosts[i], def_user, def_pass
        }
    ' "$CONFIG_FILE"
}

wanted() {
    (( ${#FILTER[@]} == 0 )) && return 0
    local f
    for f in "${FILTER[@]}"; do
        [[ $f == "$1" ]] && return 0
    done
    return 1
}

HOSTS=(); USERS=(); PASSWORDS=()
needs_sshpass=0

while IFS=$'\t' read -r host user password; do
    [[ -n $host ]] || continue
    [[ -n $user ]] || die "no user in ${CONFIG_FILE##*/} (set defaults.user)"
    wanted "$host" || continue
    HOSTS+=("$host"); USERS+=("$user"); PASSWORDS+=("$password")
    [[ -n $password ]] && needs_sshpass=1
done < <(parse_nodes)

(( ${#HOSTS[@]} > 0 )) || die "no nodes selected (check ${CONFIG_FILE##*/} and the hosts given)"

if (( needs_sshpass )) && ! command -v sshpass >/dev/null; then
    msg="sshpass is not installed (sudo apt-get install -y sshpass), or remove the passwords to use SSH keys"
    (( DRY_RUN )) && warn "$msg" || die "$msg"
fi

# ---------------------------------------------------------------------------
# Environment manifest
#
# The lab computers get the repository's own pyproject.toml, minus the editable
# install of the "pids" package: that one resolves to src/pids/, which is not
# deployed, and "pixi install" fails to build it. Everything else -- python
# version, channels, dependencies -- comes straight from pyproject.toml, so
# there is no second dependency list to keep in sync.
#
# When pixi is available here, the environment is also locked once, on the
# master, and the lock is shipped to every node: they then install exactly the
# same versions instead of each one solving on its own.
# ---------------------------------------------------------------------------

prepare_manifest() {
    MANIFEST_DIR=$(mktemp -d) || die "could not create a temporary folder"
    trap 'rm -rf "$MANIFEST_DIR"' EXIT

    awk '
        /^[[:space:]]*\[/ { table = $0; sub(/^[[:space:]]+/, "", table) }
        table ~ /pypi-dependencies\]$/ && /path[[:space:]]*=[[:space:]]*"\."/ { next }
        { print }
    ' "$PYPROJECT_SRC" > "$MANIFEST_DIR/pyproject.toml" \
        || die "could not read $PYPROJECT_SRC"

    (( DRY_RUN )) && return 0

    if ! command -v pixi >/dev/null; then
        warn "pixi is not installed here: every node will solve the environment on its own"
        warn "install it with:  curl -fsSL https://pixi.sh/install.sh | bash"
        return 0
    fi

    info "locking the environment once, here"
    if ( cd "$MANIFEST_DIR" && pixi lock >/dev/null ); then
        MANIFEST_FILES+=(pixi.lock)
    else
        warn "pixi lock failed: every node will solve the environment on its own"
    fi
}

# ---------------------------------------------------------------------------
# Remote execution
# ---------------------------------------------------------------------------

# ssh_exec <host> <user> <password> <command...>   (empty password -> SSH key)
# The password goes through the environment, not the command line, so it does
# not show up in the output of ps.
ssh_exec() {
    local host=$1 user=$2 password=$3
    shift 3
    if [[ -n $password ]]; then
        SSHPASS="$password" sshpass -e ssh "${SSH_OPTS[@]}" "$user@$host" "$@"
    else
        ssh "${SSH_OPTS[@]}" "$user@$host" "$@"
    fi
}

# ---------------------------------------------------------------------------
# Python environment
#
# pixi keeps the environment next to its manifest (week3/.pixi), so it is
# deleted and rebuilt with the code. Rebuilding downloads a couple of GB per
# node, which is why an environment that is already there is only rebuilt when
# asked for: keeping it means wiping everything except week3/.pixi.
# ---------------------------------------------------------------------------

ENV_CHOICE=""   # "", "all" or "none": answer remembered for the rest of the run

# want_env_rebuild <host> <has_env>   -> 0 = (re)build it, 1 = keep what is there
want_env_rebuild() {
    local host=$1 has_env=$2 reply

    (( has_env ))   || return 0     # nothing installed yet
    (( FORCE_ENV )) && return 0

    [[ $ENV_CHOICE == all  ]] && return 0
    [[ $ENV_CHOICE == none ]] && return 1

    if (( ASSUME_YES )); then       # unattended: keep it, it is the cheap side
        return 1
    fi

    read -r -p "    pixi environment already installed on $host. Rebuild it? [y/N/a=all/s=skip all] " reply
    case $reply in
        [yY]*) return 0 ;;
        [aA]*) ENV_CHOICE=all;  return 0 ;;
        [sS]*) ENV_CHOICE=none; return 1 ;;
        *)     return 1 ;;
    esac
}

# The remote half of "pixi install". Two different ".pixi" folders are involved:
#
#   ~/.pixi/bin/pixi            the pixi TOOL, installed on the fly when the
#                               node does not have it yet. Its installer puts it
#                               there, and a non-interactive ssh session does
#                               not have that folder in PATH, hence the export.
#   <dest>/.pixi/envs/default   the ENVIRONMENT, created by "pixi install" next
#                               to the manifest, which is why it runs from
#                               /home/<user>/robomaster/week3.
PIXI_INSTALL_SNIPPET='set -e
export PATH="$HOME/.pixi/bin:$PATH"
if ! command -v pixi >/dev/null 2>&1; then
    echo "    installing pixi"
    curl -fsSL https://pixi.sh/install.sh | bash >/dev/null
    export PATH="$HOME/.pixi/bin:$PATH"
fi
cd "__DEST__"
pixi install'

# Written into week3/.vscode/settings.json on every node. It pins the
# interpreter (the extension's own auto-detection needs the workspace to be
# opened exactly on week3/) and hides the pixi plumbing from the explorer.
VSCODE_SETTINGS='{
    "python.defaultInterpreterPath": "${workspaceFolder}/.pixi/envs/default/bin/python",
    "files.exclude": {
        "**/.pixi": true,
        "pixi.lock": true,
        "pyproject.toml": true
    },
    "python.languageServer": "Pylance",
    "python.analysis.indexing": true
}'

# deploy_node <host> <user> <password>
deploy_node() {
    local host=$1 user=$2 password=$3
    local home="/home/$user"
    local dest="$home/$DEST_NAME"
    local work="$dest/week3"        # code and environment both live here

    if (( DRY_RUN )); then
        info "would delete  $user@$host:$dest"
        info "would copy    ${WEEK3_SRC#"$REPO_DIR"/}/ -> $work"
        info "would install the pixi environment in $work (asked per node when one is already there)"
        info "would write   $work/.vscode/settings.json"
        info "would create  $dest/models (empty, for the week 2 checkpoint)"
        info "would copy    ${LABELIMG_SRC#"$REPO_DIR"/} -> $dest/labeling/labelimg.sh"
        return 0
    fi

    # Reachable, and the credentials work?
    if ! ssh_exec "$host" "$user" "$password" true </dev/null 2>/dev/null; then
        err "$host: cannot log in as '$user' over ssh"
        return 1
    fi

    # Is there an environment there already?
    local has_env=0
    ssh_exec "$host" "$user" "$password" "test -d '$work/.pixi/envs'" </dev/null 2>/dev/null && has_env=1

    local rebuild_env=0
    want_env_rebuild "$host" "$has_env" && rebuild_env=1

    # 1. Remove the previous content. Everything the students left goes away,
    #    the week 2 checkpoints in models/ included; only the environment
    #    survives, and only when it is not being rebuilt. Keeping it means
    #    emptying robomaster/ except week3/, and week3/ except .pixi -- which
    #    exists whenever has_env is 1, the only way to reach this branch.
    local wipe
    if (( rebuild_env )); then
        wipe="rm -rf '$dest'"
    else
        wipe="find '$dest' -mindepth 1 -maxdepth 1 ! -name week3 -exec rm -rf {} + &&
              find '$work' -mindepth 1 -maxdepth 1 ! -name .pixi -exec rm -rf {} +"
    fi
    if ! ssh_exec "$host" "$user" "$password" "$wipe" </dev/null; then
        err "$host: could not clean $dest"
        return 1
    fi

    # 2. Copy week3 in. models/ is created next to it, empty: demo.py reads the
    #    checkpoint as '../models/<model>/model_best.pt', relative to week3/.
    if ! ssh_exec "$host" "$user" "$password" "mkdir -p '$work' '$dest/models'" </dev/null; then
        err "$host: could not create $work"
        return 1
    fi

    if ! tar -C "$(dirname "$WEEK3_SRC")" "${TAR_EXCLUDES[@]}" \
             -cf - "$(basename "$WEEK3_SRC")" \
         | ssh_exec "$host" "$user" "$password" "tar -C '$dest' -xf -"; then
        err "$host: could not copy week3 into $dest"
        return 1
    fi

    # 3. Install the environment. The manifest is copied first: it is what pixi
    #    reads. When the environment is kept, the manifest is still refreshed,
    #    so re-run with --force-env after changing pyproject.toml.
    if ! tar -C "$MANIFEST_DIR" -cf - "${MANIFEST_FILES[@]}" \
         | ssh_exec "$host" "$user" "$password" "tar -C '$work' -xf -"; then
        err "$host: could not copy the pixi manifest"
        return 1
    fi

    if (( rebuild_env )); then
        info "installing the pixi environment (this downloads a couple of GB)"
        if ! ssh_exec "$host" "$user" "$password" \
                "${PIXI_INSTALL_SNIPPET//__DEST__/$work}" </dev/null; then
            err "$host: pixi install failed"
            return 1
        fi
    else
        info "pixi environment kept (--force-env rebuilds it)"
    fi

    # 4. Point VS Code at that environment
    if ! printf '%s\n' "$VSCODE_SETTINGS" \
         | ssh_exec "$host" "$user" "$password" \
               "mkdir -p '$work/.vscode' && cat > '$work/.vscode/settings.json'"; then
        err "$host: could not write $work/.vscode/settings.json"
        return 1
    fi

    # 5. Copy labelimg.sh into its own folder
    if ! ssh_exec "$host" "$user" "$password" \
            "mkdir -p '$dest/labeling' && cat > '$dest/labeling/labelimg.sh' \
             && chmod 755 '$dest/labeling/labelimg.sh'" < "$LABELIMG_SRC"; then
        err "$host: could not copy labelimg.sh into $dest/labeling"
        return 1
    fi

    ok "$host: $dest regenerated"
    return 0
}

# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------

echo
echo "${BOLD}Code${RESET}    ${WEEK3_SRC#"$REPO_DIR"/}/  +  ${LABELIMG_SRC#"$REPO_DIR"/}"
echo "${BOLD}Env${RESET}     ${PYPROJECT_SRC#"$REPO_DIR"/}  (minus the editable \"pids\" install)"
echo "${BOLD}Config${RESET}  ${CONFIG_FILE#"$REPO_DIR"/}"
echo "${BOLD}Nodes${RESET}   ${#HOSTS[@]}"
for i in "${!HOSTS[@]}"; do
    printf '    %-24s %s\n' "${HOSTS[$i]}" "${USERS[$i]}@ -> /home/${USERS[$i]}/$DEST_NAME"
done
echo

if (( DRY_RUN )); then
    warn "dry run: nothing will be modified"
elif (( ! ASSUME_YES )); then
    echo "${RED}This DELETES /home/<user>/$DEST_NAME on every node listed above.${RESET}"
    echo "Anything the students left there is lost."
    read -r -p "Continue? [y/N] " reply
    [[ $reply == [yY] || $reply == [yY][eE][sS] ]] || die "aborted"
    echo
fi

# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

prepare_manifest

DONE=(); FAILED=()

for i in "${!HOSTS[@]}"; do
    echo "${BOLD}--> ${HOSTS[$i]}${RESET}"
    if deploy_node "${HOSTS[$i]}" "${USERS[$i]}" "${PASSWORDS[$i]}"; then
        DONE+=("${HOSTS[$i]}")
    else
        FAILED+=("${HOSTS[$i]}")
    fi
done

echo
echo "${BOLD}Summary${RESET}"
echo "    ok      ${#DONE[@]}${DONE[*]:+  (${DONE[*]})}"
echo "    failed  ${#FAILED[@]}${FAILED[*]:+  (${FAILED[*]})}"
echo

if (( ${#FAILED[@]} > 0 )); then
    warn "re-run only the failed ones with:  ${0##*/} ${FAILED[*]}"
    exit 1
fi
