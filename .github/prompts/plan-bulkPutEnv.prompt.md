## Plan: Bulk-only PUT /envs with restart toggle

Keep only bulk updates, add `recreate_services` (default true), preserve `updated` list even if empty, and keep response message text unchanged.

### Steps
1. Update models in src/base_deployment_controller/models/environment.py: remove single-update schema, add `recreate_services` (default true) to bulk request, keep `updated` in response.
2. Refine PUT handler in src/base_deployment_controller/routers/environment.py to accept bulk-only payload, honor `recreate_services` to skip recreation, and always return `updated`; leave response message untouched.
3. Refresh docs in README.md and rest-api-endpoints.md to show payload `{ "variables": { ... }, "recreate_services": false }`, default true, and `updated` behavior.
4. Adjust tests in tests/test_api_integration.py to remove single-var flow, add `recreate_services: false` coverage, and assert `updated` presence.

### Further Considerations
1. No message change; clarify only through docs and defaults.
