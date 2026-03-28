from django.db import models

from utils import utils_time
from utils.utils_require import MAX_CHAR_LENGTH


class User(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=MAX_CHAR_LENGTH, unique=True)
    password = models.CharField(max_length=MAX_CHAR_LENGTH)
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    created_time = models.FloatField(default=utils_time.get_timestamp)

    class Meta:
        db_table = "users"
        indexes = [models.Index(fields=["name"], name="users_name_idx")]

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "createdAt": self.created_time,
        }

    def __str__(self) -> str:
        return self.name
