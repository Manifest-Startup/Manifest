# Production Setup Guide

## Environment Variables

For production deployment, you need to set the following environment variables:

### Required Environment Variables

1. **GraphQL API Endpoint** (Optional - auto-detected)
   ```bash
   REACT_APP_GRAPHQL_URL=https://manifeststartup.com/graphql
   ```
   
   If not set, the app will automatically detect if it's running on `manifeststartup.com` and use the same domain for the API.

### How It Works

The frontend defaults to the same-origin GraphQL endpoint:

1. **Default behavior**:
   - Uses: `/graphql`
   - This works when the frontend is served by the same backend origin in production.

2. **Development with a separate frontend dev server**:
   - The Vite dev server proxies `/graphql` to the backend.

3. **Custom Environment**:
   - Set `REACT_APP_GRAPHQL_URL` to override auto-detection

### Building for Production

```bash
# Set environment variable (if needed)
export REACT_APP_GRAPHQL_URL=https://manifeststartup.com/graphql

# Build the app
npm run build

# The build will include the correct GraphQL endpoint
```

### Troubleshooting

If you see "Load failed" or network errors in production:

1. **Check the GraphQL endpoint**:
   - Open browser console
   - Look for: `[Apollo] Using GraphQL endpoint: ...`
   - Verify it's pointing to the correct production URL

2. **Check CORS settings**:
   - Ensure backend allows requests from your production domain
   - Set `FRONTEND_ORIGINS` (comma-separated) on the backend; see `render.yaml`

3. **Check network tab**:
   - Open DevTools → Network
   - Look for failed GraphQL requests
   - Check the request URL and response

4. **Verify backend is running**:
   - Ensure the backend API is accessible at the GraphQL endpoint
   - Test: `curl https://manifeststartup.com/graphql` (should return GraphQL error, not 404)

### Common Issues

**Issue**: "Unable to connect to server"
- **Solution**: Check that the backend is running and accessible
- Verify the GraphQL endpoint URL is correct

**Issue**: "API endpoint not found" (404)
- **Solution**: Ensure the backend route `/graphql` exists
- Check backend routing configuration

**Issue**: CORS errors
- **Solution**: Add your production domain to `CORS_ORIGINS` in backend settings
- Ensure `CORS_CREDENTIALS: true` is set
