from django.contrib import admin

# Register your models here.
from .models import Mentor, Paper
admin.site.register(Mentor)
admin.site.register(Paper)
