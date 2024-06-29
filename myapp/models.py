from django.db import models


class LogEntry(models.Model):
    timestamp = models.DateTimeField()
    log_time = models.CharField(max_length=100)
    ip = models.GenericIPAddressField()
    status = models.CharField(max_length=20)
    bias = models.IntegerField()

    def __str__(self):
        return f"{self.timestamp} - {self.ip} - {self.status} - {self.location}"
