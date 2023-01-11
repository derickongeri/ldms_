from rest_framework.parsers import FileUploadParser

class ShapeFileParser(FileUploadParser):
    media_type = ""

