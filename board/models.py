from django.db import models
from account.models import User

# Create your models here.

class Board(models.Model):
    # TODO Start: [Student] Finish the model of Board
    
    # id, BigAutoField, primary_key=True
    # user, ForeignKey to User, CASCADE deletion
    # board_state, CharField
    # board_name, CharField
    # created_time, FloatField, default=utils_time.get_timestamp
    
    # Meta data
    # Create index on board_name
    # Create unique_together on user and board_name
    
    # TODO End: [Student] Finish the model of Board


    def serialize(self):
        username = self.user.name
        return {
            "id": self.id,
            "board": self.board_state, 
            "boardName": self.board_name,
            "username": username,
            "createdAt": self.created_time
        }

    def __str__(self) -> str:
        return f"{self.user.name}'s board {self.board_name}"
