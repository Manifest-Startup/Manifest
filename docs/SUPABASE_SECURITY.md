# Supabase Security Configuration

This document outlines the security recommendations from Supabase and how to address them.

## ✅ Fixed Issues

### 1. Function Search Path Mutable (FIXED)

**Issue**: Function `public.handle_new_user` had a mutable search_path, which can lead to search_path injection attacks.

**Status**: ✅ **FIXED** - Migration created: `supabase/migrations/20250121000000_fix_handle_new_user_security.sql`

The function now explicitly sets `search_path = public, pg_temp` to prevent injection attacks.

**Reference**: https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable

---

## ⚙️ Dashboard Configuration Required

The following issues require configuration changes in the Supabase Dashboard. These cannot be fixed via migrations and must be configured manually.

### 2. Leaked Password Protection Disabled

**Issue**: Leaked password protection is currently disabled. Supabase Auth can prevent the use of compromised passwords by checking against HaveIBeenPwned.org.

**Severity**: WARN  
**Category**: SECURITY

**How to Fix**:
1. Go to your Supabase Dashboard
2. Navigate to **Authentication** → **Policies** (or **Settings** → **Auth**)
3. Find the **Password Security** section
4. Enable **"Leaked Password Protection"** or **"Check passwords against HaveIBeenPwned"**
5. Save the changes

**Reference**: https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection

---

### 3. Insufficient MFA Options

**Issue**: Your project has too few multi-factor authentication (MFA) options enabled, which may weaken account security.

**Severity**: WARN  
**Category**: SECURITY

**How to Fix**:
1. Go to your Supabase Dashboard
2. Navigate to **Authentication** → **Settings** (or **Auth** → **Providers**)
3. Find the **Multi-Factor Authentication (MFA)** section
4. Enable additional MFA methods:
   - **TOTP (Time-based One-Time Password)** - Recommended
   - **SMS** - If phone verification is available
   - **Email OTP** - For email-based verification
5. Configure each enabled method according to your security requirements
6. Save the changes

**Reference**: https://supabase.com/docs/guides/auth/auth-mfa

---

### 4. Vulnerable Postgres Version

**Issue**: Current Postgres version (supabase-postgres-15.8.1.079) has outstanding security patches available.

**Severity**: WARN  
**Category**: SECURITY

**How to Fix**:
1. Go to your Supabase Dashboard
2. Navigate to **Settings** → **Database** (or **Project Settings** → **Database**)
3. Check for available database updates
4. If an upgrade is available, click **"Upgrade Database"** or **"Apply Updates"**
5. Review the upgrade notes and breaking changes (if any)
6. Schedule the upgrade during a maintenance window if recommended
7. Backup your database before upgrading (Supabase may do this automatically)

**Note**: Database upgrades may require brief downtime. Plan accordingly.

**Reference**: https://supabase.com/docs/guides/platform/upgrading

---

## Summary Checklist

- [x] Fix `handle_new_user` function search_path (Migration created)
- [ ] Enable leaked password protection in Supabase Dashboard
- [ ] Enable additional MFA options in Supabase Dashboard
- [ ] Upgrade Postgres database version in Supabase Dashboard

---

## Additional Security Best Practices

While addressing the above issues, consider these additional security measures:

1. **Row Level Security (RLS)**: Ensure RLS policies are enabled on sensitive tables
2. **API Keys**: Rotate service role keys regularly and never expose them in client-side code
3. **Rate Limiting**: Configure rate limits for authentication endpoints
4. **Email Verification**: Require email verification for new user signups
5. **Password Policies**: Enforce strong password requirements (minimum length, complexity)
6. **Session Management**: Configure appropriate session timeout and refresh token policies

---

*Last updated: 2026-05-01*

