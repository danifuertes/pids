FROM danielfuertes/jupyter-k8s:latest

# Opencv-python (non-headless)
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
USER ${NB_UID}

# Otherwise albumentations calls PyPI on every import
ENV NO_ALBUMENTATIONS_UPDATE=1

# Install dependencies from pyproject.toml (skip robomaster)
COPY --chown=${NB_UID}:${NB_GID} pyproject.toml /tmp/pyproject.toml
RUN python - <<'PY' > /tmp/requirements.txt
import tomllib
with open("/tmp/pyproject.toml", "rb") as fh:
    deps = tomllib.load(fh)["project"]["dependencies"]
print("\n".join(d for d in deps if not d.startswith("robomaster")))
PY
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt /tmp/pyproject.toml

# Add contents
COPY --chown=root:root src/pids/week1/ /opt/pids/week1/
COPY --chown=root:root src/pids/week2/ /opt/pids/week2/
COPY --chown=root:root --chmod=755 docker/contents.sh \
     /usr/local/bin/before-notebook.d/contents.sh
