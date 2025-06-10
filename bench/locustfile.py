from locust import HttpUser, task, between

class SentientosUser(HttpUser):
    wait_time = between(0.5, 1)
    host = "http://localhost:5000"

    @task
    def status(self):
        self.client.get("/status")

    @task
    def metrics(self):
        self.client.get("/metrics")
