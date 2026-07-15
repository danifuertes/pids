# Seeds $HOME with the course notebooks: the PVC mounts over /home/jovyan and
# hides anything baked into the image.
# Sourced by run-hooks.sh, so no 'set -e' (it would abort the spawn).

# -n never clobbers: student edits survive, missing files are restored.
cp -rn /opt/pids/week1 /opt/pids/week2 "${HOME}/" 2>/dev/null

true
