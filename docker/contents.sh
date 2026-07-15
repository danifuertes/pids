# Seeds ~/pids with the course notebooks. The per-user PVC mounts over
# /home/jovyan and hides anything baked into the image, so they are copied in here.
#
# Sourced by the base image's run-hooks.sh, so no 'set -e': a failure would abort
# the spawn and the server would never start.

mkdir -p "${HOME}/pids"

# -n never clobbers, so student edits survive and only missing files are restored.
cp -rn /opt/pids/week1 /opt/pids/week2 "${HOME}/pids/" 2>/dev/null

true
