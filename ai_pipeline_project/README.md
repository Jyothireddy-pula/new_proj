# AI Transaction Pipeline

## Run
```bash
cd ai_pipeline_project
docker compose up --build
```

## API examples
```bash
curl -X POST -F "file=@transactions.csv" http://localhost:8000/jobs/upload
curl http://localhost:8000/jobs/<job_id>/status
curl http://localhost:8000/jobs/<job_id>/results
curl http://localhost:8000/jobs?status=COMPLETED
```
