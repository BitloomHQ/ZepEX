from functools import wraps

from rest_framework.response import Response
from rest_framework import status

from .permissions import get_user_profile, has_platform_permission


def platform_permission_required(permission_code):

    def decorator(view_func):

        @wraps(view_func)
        def wrapped(request, *args, **kwargs):

            profile = get_user_profile(request.user)

            if not has_platform_permission(
                user=request.user,
                profile=profile,
                permission_code=permission_code,
            ):
                return Response(
                    {
                        "error": "You don't have permission to perform this action."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
