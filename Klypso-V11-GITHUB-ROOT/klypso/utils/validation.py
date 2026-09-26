def validate_upload(file, max_bytes):
    if not file or not file.filename:
        raise ValueError("Aucun fichier sélectionné.")
    filename = file.filename.replace("\\", "/").split("/")[-1]
    if not filename or filename in {".", ".."}:
        raise ValueError("Nom de fichier invalide.")
    if not file.mimetype.startswith("video/"):
        raise ValueError("Le fichier doit être une vidéo.")
    content_length = getattr(file, "content_length", None)
    if content_length and content_length > max_bytes:
        raise ValueError("Fichier trop volumineux.")
