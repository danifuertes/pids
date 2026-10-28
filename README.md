# PIDS (Proyectos de Ingeniería de Datos y Sistemas)

Course project of **PIDS** in the
[Grado en Ingeniería y Sistemas de Datos](https://www.etsit.upm.es/estudios/grado-en-ingenieria-y-sistemas-de-datos.html)
of the Escuela Técnica Superior de Ingenieros de Telecomunicación (ETSIT),
Universidad Politécnica de Madrid (UPM): student groups build a robot detector
and deploy it on a DJI **RoboMaster EP**. The guides in [`guides/`](guides/)
describe how to follow the course.

## Installation

The environment is managed with [pixi](https://pixi.sh):

```bash
pixi install
```

## Usage

### Local

```bash
pixi shell
```

To annotate images, run [`labelimg/labelimg.sh`](labelimg/labelimg.sh)
(requires Docker and an X server).

### Lab: notebooks on JupyterHub

The notebooks run on a JupyterHub deployed with
[jupyter-k8s](https://github.com/danifuertes/jupyter-k8s), using the image built
from this repository's [Dockerfile](Dockerfile):

```bash
docker build -t <registry>/pids:latest .
docker push <registry>/pids:latest
```

Then add a profile with that image to the `jupyterhub:` section of the
jupyter-k8s `inputs.yaml` and apply it:

```yaml
singleuser:
  profileList:
    - display_name: "PIDS"
      kubespawner_override:
        image: <registry>/pids:latest
```

```bash
./jupyterhub/update-config.sh
./jupyterhub/create.sh
```

### Lab: robot computers

The robot scripts run on the lab computers. From the master node, copy them to
every computer listed in `lab-setup/nodes.yaml`:

```bash
cp lab-setup/nodes.example.yaml lab-setup/nodes.yaml   # then fill it in
lab-setup/deploy.sh
```

### Data

The dataset is not included. The notebooks expect `data_train/`, `data_val/`
and `data_test/` folders with one subfolder per sequence (`images/` and Pascal
VOC `labels/`). [`check_data.py`](src/pids/data/check_data.py) validates a
dataset and [`split_data.py`](src/pids/data/split_data.py) creates the three
sets.
