from supabase import create_client, Client

from config import settings


def get_supabase_admin() -> Client:
    """Return a Supabase client using the service role key (admin access).

    This bypasses RLS and should only be used in the backend.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
