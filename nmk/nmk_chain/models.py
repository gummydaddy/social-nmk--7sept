# nmk_chain/models.py

from django.db import models

class Block(models.Model):
    number = models.IntegerField()
    previous = models.CharField(max_length=64)
    data = models.TextField()
    nonce = models.IntegerField()
    hash = models.CharField(max_length=64)

    def __str__(self):
        return f"Block {self.number}"
