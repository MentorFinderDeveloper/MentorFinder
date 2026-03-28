from django.db import models

from utils import utils_time
from utils.utils_request import return_field
from utils.utils_require import MAX_CHAR_LENGTH


class User(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=MAX_CHAR_LENGTH, unique=True)
    password = models.CharField(max_length=MAX_CHAR_LENGTH)
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    created_time = models.FloatField(default=utils_time.get_timestamp)

    class Meta:
        # Reuse the existing table created earlier under the board app.
        db_table = "board_user"
        indexes = [models.Index(fields=["name"])]

    def serialize(self):
        # Local import to avoid cyclic imports between account and board models.
        from board.models import Board

        boards = Board.objects.filter(user=self)
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "createdAt": self.created_time,
            "boards": [
                return_field(board.serialize(), ["id", "boardName", "userName", "createdAt"])
                for board in boards
            ],
        }

    def __str__(self) -> str:
        return self.name
