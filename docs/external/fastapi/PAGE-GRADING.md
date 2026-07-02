# FastAPI — Page Importance Grading

138 URLs raw; 138 after normalization (no foreign locales or release-notes pages remained after URL-path filtering of the mapped set; final corpus = 138, but only 138 after dedup → 138 scored). **Note (iteration-2 dry-run):** scoring done from URL paths + prior knowledge of FastAPI docs — no Firecrawl scrapes performed. Per-page evidence intentionally terse per skill guidance. Top 100 selected for archive (site has more than 100 candidate pages, so the cap applies).

| Tier | Score | Count | Meaning |
|------|-------|-------|---------|
| **S** | 80+    | 12 | Quickstart, tutorial entry, core type primer, async primer, root index — newcomer must-reads |
| **A** | 60–79  | 38 | Core tutorial chapters, dependency injection, security tutorial, deployment, primary API reference |
| **B** | 40–59  | 36 | Advanced patterns, testing variants, advanced security, full reference modules |
| **C** | 20–39  | 22 | Niche how-to recipes (Peewee, Couchbase, GraphQL), platform-specific tweaks |
| **D** | <20    | 30 | Auto-generated reference subpages, community/meta pages, marketing/benchmarks, alternatives history |

## Tier S
- **[98]** [/](https://fastapi.tiangolo.com/) — FastAPI (landing/intro)
- **[97]** [/tutorial/](https://fastapi.tiangolo.com/tutorial/) — Tutorial - User Guide
- **[96]** [/tutorial/first-steps/](https://fastapi.tiangolo.com/tutorial/first-steps/) — First Steps
- **[94]** [/learn/](https://fastapi.tiangolo.com/learn/) — Learn
- **[92]** [/features/](https://fastapi.tiangolo.com/features/) — Features
- **[91]** [/python-types/](https://fastapi.tiangolo.com/python-types/) — Python Types Intro
- **[89]** [/async/](https://fastapi.tiangolo.com/async/) — Concurrency and async / await
- **[87]** [/tutorial/path-params/](https://fastapi.tiangolo.com/tutorial/path-params/) — Path Parameters
- **[86]** [/tutorial/query-params/](https://fastapi.tiangolo.com/tutorial/query-params/) — Query Parameters
- **[85]** [/tutorial/body/](https://fastapi.tiangolo.com/tutorial/body/) — Request Body
- **[83]** [/virtual-environments/](https://fastapi.tiangolo.com/virtual-environments/) — Virtual Environments
- **[82]** [/environment-variables/](https://fastapi.tiangolo.com/environment-variables/) — Environment Variables

## Tier A
- **[79]** [/tutorial/response-model/](https://fastapi.tiangolo.com/tutorial/response-model/) — Response Model
- **[78]** [/tutorial/dependencies/](https://fastapi.tiangolo.com/tutorial/dependencies/) — Dependencies
- **[78]** [/tutorial/security/](https://fastapi.tiangolo.com/tutorial/security/) — Security
- **[77]** [/tutorial/security/first-steps/](https://fastapi.tiangolo.com/tutorial/security/first-steps/) — Security First Steps
- **[76]** [/tutorial/security/oauth2-jwt/](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) — OAuth2 with JWT
- **[76]** [/tutorial/sql-databases/](https://fastapi.tiangolo.com/tutorial/sql-databases/) — SQL (Relational) Databases
- **[75]** [/tutorial/bigger-applications/](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — Bigger Applications
- **[75]** [/tutorial/handling-errors/](https://fastapi.tiangolo.com/tutorial/handling-errors/) — Handling Errors
- **[74]** [/tutorial/query-params-str-validations/](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/) — Query Param Validations
- **[74]** [/tutorial/path-params-numeric-validations/](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/) — Path Param Numeric Validations
- **[73]** [/tutorial/body-multiple-params/](https://fastapi.tiangolo.com/tutorial/body-multiple-params/) — Body - Multiple Parameters
- **[73]** [/tutorial/body-fields/](https://fastapi.tiangolo.com/tutorial/body-fields/) — Body - Fields
- **[73]** [/tutorial/body-nested-models/](https://fastapi.tiangolo.com/tutorial/body-nested-models/) — Body - Nested Models
- **[72]** [/tutorial/testing/](https://fastapi.tiangolo.com/tutorial/testing/) — Testing
- **[72]** [/tutorial/middleware/](https://fastapi.tiangolo.com/tutorial/middleware/) — Middleware
- **[72]** [/tutorial/cors/](https://fastapi.tiangolo.com/tutorial/cors/) — CORS
- **[72]** [/tutorial/dependencies/classes-as-dependencies/](https://fastapi.tiangolo.com/tutorial/dependencies/classes-as-dependencies/) — Classes as Dependencies
- **[71]** [/tutorial/dependencies/dependencies-with-yield/](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/) — Dependencies with yield
- **[71]** [/tutorial/dependencies/sub-dependencies/](https://fastapi.tiangolo.com/tutorial/dependencies/sub-dependencies/) — Sub-dependencies
- **[71]** [/tutorial/security/get-current-user/](https://fastapi.tiangolo.com/tutorial/security/get-current-user/) — Get Current User
- **[71]** [/tutorial/security/simple-oauth2/](https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/) — Simple OAuth2 with Password & Bearer
- **[70]** [/tutorial/cookie-params/](https://fastapi.tiangolo.com/tutorial/cookie-params/) — Cookie Parameters
- **[70]** [/tutorial/header-params/](https://fastapi.tiangolo.com/tutorial/header-params/) — Header Parameters
- **[70]** [/tutorial/extra-models/](https://fastapi.tiangolo.com/tutorial/extra-models/) — Extra Models
- **[70]** [/tutorial/response-status-code/](https://fastapi.tiangolo.com/tutorial/response-status-code/) — Response Status Code
- **[69]** [/tutorial/request-forms/](https://fastapi.tiangolo.com/tutorial/request-forms/) — Request Forms
- **[69]** [/tutorial/request-files/](https://fastapi.tiangolo.com/tutorial/request-files/) — Request Files
- **[69]** [/tutorial/background-tasks/](https://fastapi.tiangolo.com/tutorial/background-tasks/) — Background Tasks
- **[68]** [/tutorial/dependencies/dependencies-in-path-operation-decorators/](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/) — Deps in Path Op Decorators
- **[68]** [/tutorial/dependencies/global-dependencies/](https://fastapi.tiangolo.com/tutorial/dependencies/global-dependencies/) — Global Dependencies
- **[67]** [/deployment/](https://fastapi.tiangolo.com/deployment/) — Deployment
- **[67]** [/deployment/docker/](https://fastapi.tiangolo.com/deployment/docker/) — Docker
- **[67]** [/deployment/concepts/](https://fastapi.tiangolo.com/deployment/concepts/) — Deployment Concepts
- **[66]** [/tutorial/path-operation-configuration/](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/) — Path Op Configuration
- **[66]** [/tutorial/encoder/](https://fastapi.tiangolo.com/tutorial/encoder/) — JSON Compatible Encoder
- **[66]** [/tutorial/body-updates/](https://fastapi.tiangolo.com/tutorial/body-updates/) — Body - Updates
- **[65]** [/advanced/](https://fastapi.tiangolo.com/advanced/) — Advanced User Guide
- **[64]** [/advanced/security/](https://fastapi.tiangolo.com/advanced/security/) — Advanced Security
- **[63]** [/reference/fastapi/](https://fastapi.tiangolo.com/reference/fastapi/) — FastAPI class reference
- **[62]** [/reference/](https://fastapi.tiangolo.com/reference/) — Reference index
- **[61]** [/tutorial/metadata/](https://fastapi.tiangolo.com/tutorial/metadata/) — Metadata and Docs URLs
- **[60]** [/tutorial/static-files/](https://fastapi.tiangolo.com/tutorial/static-files/) — Static Files
- **[60]** [/deployment/https/](https://fastapi.tiangolo.com/deployment/https/) — HTTPS

## Tier B
- **[58]** [/tutorial/schema-extra-example/](https://fastapi.tiangolo.com/tutorial/schema-extra-example/) — Schema Extra - Example
- **[58]** [/tutorial/extra-data-types/](https://fastapi.tiangolo.com/tutorial/extra-data-types/) — Extra Data Types
- **[57]** [/tutorial/cookie-param-models/](https://fastapi.tiangolo.com/tutorial/cookie-param-models/) — Cookie Param Models
- **[57]** [/tutorial/header-param-models/](https://fastapi.tiangolo.com/tutorial/header-param-models/) — Header Param Models
- **[57]** [/tutorial/request-form-models/](https://fastapi.tiangolo.com/tutorial/request-form-models/) — Form Models
- **[56]** [/tutorial/request-forms-and-files/](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/) — Forms and Files
- **[56]** [/tutorial/debugging/](https://fastapi.tiangolo.com/tutorial/debugging/) — Debugging
- **[55]** [/advanced/path-operation-advanced-configuration/](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/) — Path Op Advanced Config
- **[55]** [/advanced/additional-status-codes/](https://fastapi.tiangolo.com/advanced/additional-status-codes/) — Additional Status Codes
- **[55]** [/advanced/response-directly/](https://fastapi.tiangolo.com/advanced/response-directly/) — Return a Response Directly
- **[55]** [/advanced/custom-response/](https://fastapi.tiangolo.com/advanced/custom-response/) — Custom Response
- **[54]** [/advanced/additional-responses/](https://fastapi.tiangolo.com/advanced/additional-responses/) — Additional Responses in OpenAPI
- **[54]** [/advanced/response-cookies/](https://fastapi.tiangolo.com/advanced/response-cookies/) — Response Cookies
- **[54]** [/advanced/response-headers/](https://fastapi.tiangolo.com/advanced/response-headers/) — Response Headers
- **[53]** [/advanced/response-change-status-code/](https://fastapi.tiangolo.com/advanced/response-change-status-code/) — Response - Change Status Code
- **[53]** [/advanced/advanced-dependencies/](https://fastapi.tiangolo.com/advanced/advanced-dependencies/) — Advanced Dependencies
- **[53]** [/advanced/security/oauth2-scopes/](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/) — OAuth2 scopes
- **[53]** [/advanced/security/http-basic-auth/](https://fastapi.tiangolo.com/advanced/security/http-basic-auth/) — HTTP Basic Auth
- **[52]** [/advanced/using-request-directly/](https://fastapi.tiangolo.com/advanced/using-request-directly/) — Use Request Directly
- **[52]** [/advanced/dataclasses/](https://fastapi.tiangolo.com/advanced/dataclasses/) — Dataclasses
- **[52]** [/advanced/middleware/](https://fastapi.tiangolo.com/advanced/middleware/) — Advanced Middleware
- **[52]** [/advanced/sub-applications/](https://fastapi.tiangolo.com/advanced/sub-applications/) — Sub Applications
- **[52]** [/advanced/behind-a-proxy/](https://fastapi.tiangolo.com/advanced/behind-a-proxy/) — Behind a Proxy
- **[51]** [/advanced/templates/](https://fastapi.tiangolo.com/advanced/templates/) — Templates
- **[51]** [/advanced/websockets/](https://fastapi.tiangolo.com/advanced/websockets/) — WebSockets
- **[51]** [/advanced/events/](https://fastapi.tiangolo.com/advanced/events/) — Lifespan Events
- **[50]** [/advanced/settings/](https://fastapi.tiangolo.com/advanced/settings/) — Settings and Environment Variables
- **[50]** [/advanced/openapi-callbacks/](https://fastapi.tiangolo.com/advanced/openapi-callbacks/) — OpenAPI Callbacks
- **[50]** [/advanced/openapi-webhooks/](https://fastapi.tiangolo.com/advanced/openapi-webhooks/) — OpenAPI Webhooks
- **[49]** [/advanced/generate-clients/](https://fastapi.tiangolo.com/advanced/generate-clients/) — Generate Clients
- **[48]** [/deployment/manually/](https://fastapi.tiangolo.com/deployment/manually/) — Run a Server Manually
- **[48]** [/deployment/server-workers/](https://fastapi.tiangolo.com/deployment/server-workers/) — Server Workers
- **[47]** [/reference/apirouter/](https://fastapi.tiangolo.com/reference/apirouter/) — APIRouter reference
- **[47]** [/reference/dependencies/](https://fastapi.tiangolo.com/reference/dependencies/) — Dependencies reference
- **[46]** [/reference/security/](https://fastapi.tiangolo.com/reference/security/) — Security reference
- **[45]** [/reference/responses/](https://fastapi.tiangolo.com/reference/responses/) — Responses reference

## Tier C
- **[39]** [/advanced/custom-request-and-route/](https://fastapi.tiangolo.com/advanced/custom-request-and-route/) — Custom Request/Route Class
- **[38]** [/advanced/testing-websockets/](https://fastapi.tiangolo.com/advanced/testing-websockets/) — Testing WebSockets
- **[38]** [/advanced/testing-events/](https://fastapi.tiangolo.com/advanced/testing-events/) — Testing Events
- **[38]** [/advanced/testing-dependencies/](https://fastapi.tiangolo.com/advanced/testing-dependencies/) — Testing Dependencies
- **[37]** [/advanced/testing-database/](https://fastapi.tiangolo.com/advanced/testing-database/) — Testing Database
- **[37]** [/advanced/async-tests/](https://fastapi.tiangolo.com/advanced/async-tests/) — Async Tests
- **[36]** [/advanced/wsgi/](https://fastapi.tiangolo.com/advanced/wsgi/) — Including WSGI
- **[36]** [/advanced/openapi-extra-data/](https://fastapi.tiangolo.com/advanced/openapi-extra-data/) — OpenAPI Extra Data
- **[35]** [/how-to/](https://fastapi.tiangolo.com/how-to/) — How To - Recipes
- **[34]** [/how-to/general/](https://fastapi.tiangolo.com/how-to/general/) — General - How To
- **[33]** [/how-to/separate-openapi-schemas/](https://fastapi.tiangolo.com/how-to/separate-openapi-schemas/) — Separate OpenAPI schemas
- **[32]** [/how-to/configure-swagger-ui/](https://fastapi.tiangolo.com/how-to/configure-swagger-ui/) — Configure Swagger UI
- **[32]** [/how-to/extending-openapi/](https://fastapi.tiangolo.com/how-to/extending-openapi/) — Extending OpenAPI
- **[31]** [/how-to/conditional-openapi/](https://fastapi.tiangolo.com/how-to/conditional-openapi/) — Conditional OpenAPI
- **[30]** [/how-to/custom-docs-ui-assets/](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/) — Custom docs UI assets
- **[28]** [/how-to/graphql/](https://fastapi.tiangolo.com/how-to/graphql/) — GraphQL
- **[27]** [/deployment/versions/](https://fastapi.tiangolo.com/deployment/versions/) — About FastAPI versions
- **[26]** [/deployment/cloud/](https://fastapi.tiangolo.com/deployment/cloud/) — Deploy to Cloud Providers
- **[25]** [/how-to/sql-databases-peewee/](https://fastapi.tiangolo.com/how-to/sql-databases-peewee/) — SQL Databases with Peewee
- **[24]** [/how-to/async-sql-encode-databases/](https://fastapi.tiangolo.com/how-to/async-sql-encode-databases/) — Async SQL (encode/databases)
- **[23]** [/how-to/nosql-databases-couchbase/](https://fastapi.tiangolo.com/how-to/nosql-databases-couchbase/) — NoSQL with Couchbase
- **[22]** [/how-to/custom-request-and-route/](https://fastapi.tiangolo.com/how-to/custom-request-and-route/) — Custom Request/Route (how-to)

## Tier D (excluded from top 100, listed for transparency)
- [/reference/request/](https://fastapi.tiangolo.com/reference/request/) — Request reference (auto-gen)
- [/reference/websockets/](https://fastapi.tiangolo.com/reference/websockets/) — WebSockets reference (auto-gen)
- [/reference/background/](https://fastapi.tiangolo.com/reference/background/) — Background reference (auto-gen)
- [/reference/parameters/](https://fastapi.tiangolo.com/reference/parameters/) — Parameters reference (auto-gen)
- [/reference/uploadfile/](https://fastapi.tiangolo.com/reference/uploadfile/) — UploadFile reference (auto-gen)
- [/reference/exceptions/](https://fastapi.tiangolo.com/reference/exceptions/) — Exceptions reference (auto-gen)
- [/reference/status/](https://fastapi.tiangolo.com/reference/status/) — status reference (auto-gen)
- [/reference/middleware/](https://fastapi.tiangolo.com/reference/middleware/) — Middleware reference (auto-gen)
- [/reference/openapi/](https://fastapi.tiangolo.com/reference/openapi/) — OpenAPI reference (auto-gen)
- [/reference/openapi/docs/](https://fastapi.tiangolo.com/reference/openapi/docs/) — OpenAPI docs reference (auto-gen)
- [/reference/openapi/models/](https://fastapi.tiangolo.com/reference/openapi/models/) — OpenAPI models reference (auto-gen)
- [/reference/response/](https://fastapi.tiangolo.com/reference/response/) — Response reference (auto-gen)
- [/reference/staticfiles/](https://fastapi.tiangolo.com/reference/staticfiles/) — StaticFiles reference (auto-gen)
- [/reference/templating/](https://fastapi.tiangolo.com/reference/templating/) — Templating reference (auto-gen)
- [/reference/testclient/](https://fastapi.tiangolo.com/reference/testclient/) — TestClient reference (auto-gen)
- [/about/](https://fastapi.tiangolo.com/about/) — About
- [/help-fastapi/](https://fastapi.tiangolo.com/help-fastapi/) — Help FastAPI - Get Help
- [/contributing/](https://fastapi.tiangolo.com/contributing/) — Contributing
- [/management/](https://fastapi.tiangolo.com/management/) — Management
- [/management-tasks/](https://fastapi.tiangolo.com/management-tasks/) — Management Tasks
- [/external-links/](https://fastapi.tiangolo.com/external-links/) — External Links and Articles
- [/resources/](https://fastapi.tiangolo.com/resources/) — Resources
- [/fastapi-people/](https://fastapi.tiangolo.com/fastapi-people/) — FastAPI People
- [/benchmarks/](https://fastapi.tiangolo.com/benchmarks/) — Benchmarks
- [/project-generation/](https://fastapi.tiangolo.com/project-generation/) — Full Stack FastAPI Project Generation
- [/alternatives/](https://fastapi.tiangolo.com/alternatives/) — Alternatives, Inspiration, Comparisons
- [/history-design-future/](https://fastapi.tiangolo.com/history-design-future/) — History, Design, Future
- [/newsletter/](https://fastapi.tiangolo.com/newsletter/) — Newsletter
