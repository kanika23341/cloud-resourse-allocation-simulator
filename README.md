# CloudLab — Cloud Resource Scheduling Simulator

CloudLab is a local, persistent cloud-systems simulator built with FastAPI, SQLite, and HTML/CSS/JavaScript.

## Features

- VM placement using First Fit and Best Fit, with persistent allocation history.
- Simulated EC2 instance catalogue.
- Persistent object storage with six storage tiers and estimated monthly cost/latency.
- Configurable database sharding, asynchronous read replicas, synchronous or asynchronous backups, and optional read cache.
- Read routing through a simulated round-robin load balancer.
- Availability-zone and shard placement visualization.
- Simulation metrics and activity log.
- SQLite database persists between backend restarts.

## How to run
Open a terminal in the extracted `CloudLab` directory:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `frontend/index.html` in a browser


## Database

The SQLite file is created automatically at `backend/cloudlab.db`. To reset all simulated cloud state, stop the server and delete this file, then re-start backend.

## API 

- `GET /health`
- `GET /servers`, `POST /allocate`, `POST /reset`, `GET /metrics`
- `GET /ec2/instances`
- `GET/POST /cloud/storage`, `DELETE /cloud/storage/{id}`, `GET /cloud/storage/types`
- `POST /cloud/database/configure`, `GET /cloud/database`
- `POST /cloud/database/write`, `GET /cloud/database/read/{key}`
- `GET /cloud/database/backups`, `GET /cloud/database/replicas`
- `GET /cloud/load-balancer`, `GET /cloud/zones`
- `GET /cloud/activity`

