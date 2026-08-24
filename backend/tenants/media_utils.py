def profile_picture_url(profile, request=None):
    if not profile or not profile.profile_picture:
        return None

    try:
        url = profile.profile_picture.url
    except (ValueError, OSError):
        return None
    if request:
        return request.build_absolute_uri(url)
    return url
