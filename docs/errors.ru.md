# Errors — Русский

`48` error keys. Canonical texts live in the code (`register_service_errors`); localized texts in `translations/errors.ru.json`.

| Код | Статус | Параметры | Действие | Текст |
|---|---|---|---|---|
| `error.400.bad_request` | 400 | — | `fix_input` | Bad request _(en)_ |
| `error.400.captcha_invalid` | 400 | — | `retry` | Captcha verification failed. Please try again. _(en)_ |
| `error.400.captcha_required` | 400 | — | `retry` | Captcha token is required. _(en)_ |
| `error.400.expected_list` | 400 | — | `fix_input` | Expected a list of items _(en)_ |
| `error.400.field.blank` | 400 | `field` | `fix_input` | {field} may not be blank _(en)_ |
| `error.400.field.does_not_exist` | 400 | `field` | `fix_input` | {field} does not exist _(en)_ |
| `error.400.field.invalid` | 400 | `field` | `fix_input` | {field} is invalid _(en)_ |
| `error.400.field.invalid_choice` | 400 | `field` | `fix_input` | {field} is not a valid choice _(en)_ |
| `error.400.field.max_length` | 400 | `field`, `max_length` | `fix_input` | {field} must be at most {max_length} characters _(en)_ |
| `error.400.field.max_value` | 400 | `field`, `max_value` | `fix_input` | {field} must be at most {max_value} _(en)_ |
| `error.400.field.min_length` | 400 | `field`, `min_length` | `fix_input` | {field} must be at least {min_length} characters _(en)_ |
| `error.400.field.min_value` | 400 | `field`, `min_value` | `fix_input` | {field} must be at least {min_value} _(en)_ |
| `error.400.field.null` | 400 | `field` | `fix_input` | {field} may not be null _(en)_ |
| `error.400.field.required` | 400 | `field` | `fix_input` | {field} is required _(en)_ |
| `error.400.field.unique` | 400 | `field` | `fix_input` | {field} must be unique _(en)_ |
| `error.400.geohash_required` | 400 | — | `fix_input` | Geohash is required _(en)_ |
| `error.400.invalid_ad_id` | 400 | — | `fix_input` | Invalid advertisement ID _(en)_ |
| `error.400.invalid_geojson` | 400 | — | `fix_input` | GeoJSON file is invalid _(en)_ |
| `error.400.invalid_import_status` | 400 | — | `fix_input` | Cannot retry import with current status _(en)_ |
| `error.400.invalid_params` | 400 | — | `fix_input` | One or more query parameters are invalid _(en)_ |
| `error.400.lat_lon_required` | 400 | — | `fix_input` | Valid latitude and longitude are required _(en)_ |
| `error.400.uuid_required` | 400 | — | `fix_input` | Location UUID is required _(en)_ |
| `error.400.validation_error` | 400 | — | `fix_input` | Validation error _(en)_ |
| `error.400.verification_failed` | 400 | — | `verify` | Verification failed _(en)_ |
| `error.400.verification_invalid_factor` | 400 | — | `verify` | This verification factor is not available _(en)_ |
| `error.401.unauthorized` | 401 | — | `reauthenticate` | Authentication required _(en)_ |
| `error.402.payment_required` | 402 | — | `retry` | Payment required _(en)_ |
| `error.403.forbidden` | 403 | — | `retry` | You do not have permission to perform this action _(en)_ |
| `error.403.network_blocked` | 403 | — | `contact_support` | Requests from this network are not allowed _(en)_ |
| `error.403.verification_enrollment_required` | 403 | — | `verify` | Verification factor enrollment required _(en)_ |
| `error.403.verification_required` | 403 | — | `verify` | Additional verification required _(en)_ |
| `error.404.ad_not_found` | 404 | — | `retry` | Listing not found _(en)_ |
| `error.404.not_found` | 404 | — | `retry` | Requested resource not found _(en)_ |
| `error.404.verification_challenge_not_found` | 404 | — | `verify` | Verification challenge not found or expired _(en)_ |
| `error.405.method_not_allowed` | 405 | — | `retry` | Method not allowed _(en)_ |
| `error.406.not_acceptable` | 406 | — | `retry` | Not acceptable _(en)_ |
| `error.408.request_timeout` | 408 | — | `retry` | Request timeout _(en)_ |
| `error.409.conflict` | 409 | — | `fix_input` | Resource already exists _(en)_ |
| `error.410.gone` | 410 | — | `retry` | Resource has been permanently removed _(en)_ |
| `error.413.payload_too_large` | 413 | — | `retry` | Request body is too large _(en)_ |
| `error.415.unsupported_media_type` | 415 | — | `retry` | Unsupported media type _(en)_ |
| `error.422.unprocessable_entity` | 422 | — | `wait_and_retry` | Unprocessable entity _(en)_ |
| `error.423.locked` | 423 | — | `wait_and_retry` | Resource is locked _(en)_ |
| `error.423.verification_locked` | 423 | — | `wait_and_retry` | Too many failed attempts — verification locked _(en)_ |
| `error.429.rate_limit` | 429 | `retry_after_minutes` | `wait_and_retry` | Too many attempts. Try again in {retry_after_minutes} minutes. _(en)_ |
| `error.429.too_many_requests` | 429 | — | `wait_and_retry` | Too many requests. Please try again later. _(en)_ |
| `error.500.internal` | 500 | — | `contact_support` | Something went wrong _(en)_ |
| `error.502.geocoder_unavailable` | 502 | — | `retry` | Geocoding provider is unavailable _(en)_ |
