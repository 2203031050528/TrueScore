from rest_framework_simplejwt.tokens import RefreshToken


def tokens_for(user):
    """Refresh + access pair carrying the user's role and token_version."""
    refresh = RefreshToken.for_user(user)
    refresh["tv"] = user.token_version
    refresh["role"] = user.role
    access = refresh.access_token
    # The access token copies custom claims from the refresh token in SimpleJWT >= 5.
    access["tv"] = user.token_version
    access["role"] = user.role
    return refresh, access
