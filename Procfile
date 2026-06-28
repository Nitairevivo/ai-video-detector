web: uvicorn api.server:app --host 0.0.0.0 --port $PORT
worker: python train_forever.py --max 10000 --batch 30 --workers 4
