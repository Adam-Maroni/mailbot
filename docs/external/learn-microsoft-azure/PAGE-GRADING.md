# Microsoft Azure + Graph (API-connectivity scope) — Page Importance Grading
150 pages pre-ranked via URL heuristics from 1335 normalized URLs (corpus: Azure root + Microsoft Graph, filtered to API-connectivity / Outlook scope). Top 100 selected for archive.

**Scoring method:** URL-path heuristics (no per-page preview scrapes). Path structure on `learn.microsoft.com` is strongly predictive of content type, so heuristic scoring is a credit-saving proxy for LLM preview scoring. Scores are relative within this corpus.

| Tier | Score | Count | Meaning |
|------|-------|-------|---------|
| **S** | 100+   | 15 | Outlook mail/calendar Graph pages, auth concepts, delta-query overview, Graph tutorials |
| **A** | 80-99  | 10 | Core Graph API resources (message, event, mailfolder), identity-platform develop docs, Outlook-specific guides |
| **B** | 60-79  | 75 | API Management how-tos, secondary Graph resources, Logic Apps connectors, Functions HTTP triggers |
| **C** | 40-59  | 0 | Supporting concepts: Communication Services, Key Vault, webhook plumbing, Entra ID general |
| **D** | <40    | 0 | Niche/edge pages — not expected in top-100 |

## Tier S
- **[130]** [/en-us/graph/outlook-calendar-online-meetings](https://learn.microsoft.com/en-us/graph/outlook-calendar-online-meetings) — Outlook Calendar Online Meetings
- **[130]** [/en-us/graph/outlook-get-mime-message](https://learn.microsoft.com/en-us/graph/outlook-get-mime-message) — Outlook Get Mime Message
- **[130]** [/en-us/graph/outlook-schedule-recurring-events](https://learn.microsoft.com/en-us/graph/outlook-schedule-recurring-events) — Outlook Schedule Recurring Events
- **[115]** [/en-us/graph/auth-v2-service](https://learn.microsoft.com/en-us/graph/auth-v2-service) — Auth V2 Service
- **[115]** [/en-us/graph/auth-v2-user](https://learn.microsoft.com/en-us/graph/auth-v2-user) — Auth V2 User
- **[115]** [/en-us/graph/auth/auth-concepts](https://learn.microsoft.com/en-us/graph/auth/auth-concepts) — Auth Concepts
- **[115]** [/en-us/graph/delta-query-groups](https://learn.microsoft.com/en-us/graph/delta-query-groups) — Delta Query Groups
- **[115]** [/en-us/graph/delta-query-overview](https://learn.microsoft.com/en-us/graph/delta-query-overview) — Delta Query Overview
- **[105]** [/en-us/graph/overview](https://learn.microsoft.com/en-us/graph/overview) — Overview
- **[100]** [/en-us/graph/tutorials/azure-functions](https://learn.microsoft.com/en-us/graph/tutorials/azure-functions?tutorial-step=3) — Azure Functions
- **[100]** [/en-us/graph/tutorials/bot-framework](https://learn.microsoft.com/en-us/graph/tutorials/bot-framework?tutorial-step=2) — Bot Framework
- **[100]** [/en-us/graph/tutorials/php-email](https://learn.microsoft.com/en-us/graph/tutorials/php-email) — Php Email
- **[100]** [/en-us/graph/tutorials/python-email](https://learn.microsoft.com/en-us/graph/tutorials/python-email) — Python Email
- **[100]** [/en-us/graph/tutorials/typescript-authentication](https://learn.microsoft.com/en-us/graph/tutorials/typescript-authentication) — Typescript Authentication
- **[100]** [/en-us/graph/tutorials/uwp](https://learn.microsoft.com/en-us/graph/tutorials/uwp) — Uwp

## Tier A
- **[90]** [/en-us/graph/api/resources/calendar-overview](https://learn.microsoft.com/en-us/graph/api/resources/calendar-overview) — Calendar Overview
- **[90]** [/en-us/graph/api/resources/event](https://learn.microsoft.com/en-us/graph/api/resources/event) — Event
- **[90]** [/en-us/graph/api/resources/mail-api-overview](https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview) — Mail Api Overview
- **[90]** [/en-us/graph/api/resources/mailfolder](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder) — Mailfolder
- **[90]** [/en-us/graph/api/resources/message](https://learn.microsoft.com/en-us/graph/api/resources/message) — Message
- **[90]** [/en-us/graph/sdks/choose-authentication-providers](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) — Choose Authentication Providers
- **[90]** [/en-us/graph/sdks/national-clouds](https://learn.microsoft.com/en-us/graph/sdks/national-clouds) — National Clouds
- **[90]** [/en-us/graph/use-the-api](https://learn.microsoft.com/en-us/graph/use-the-api) — Use The Api
- **[85]** [/en-us/graph/permissions-reference](https://learn.microsoft.com/en-us/graph/permissions-reference) — Permissions Reference
- **[80]** [/en-us/azure/communication-services/concepts/email/email-overview](https://learn.microsoft.com/en-us/azure/communication-services/concepts/email/email-overview) — Email Overview

## Tier B
- **[75]** [/en-us/azure/api-management/api-management-howto-protect-backend-with-aad](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-protect-backend-with-aad) — Api Management Howto Protect Backend With Aad
- **[75]** [/en-us/azure/api-management/api-management-key-concepts](https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts) — Api Management Key Concepts
- **[75]** [/en-us/azure/api-management/api-management-subscriptions](https://learn.microsoft.com/en-us/azure/api-management/api-management-subscriptions) — Api Management Subscriptions
- **[75]** [/en-us/graph/api/overview](https://learn.microsoft.com/en-us/graph/api/overview) — Overview
- **[75]** [/en-us/graph/mcp-server/overview](https://learn.microsoft.com/en-us/graph/mcp-server/overview) — Overview
- **[75]** [/en-us/graph/templates/terraform/overview-terraform-for-graph](https://learn.microsoft.com/en-us/graph/templates/terraform/overview-terraform-for-graph) — Overview Terraform For Graph
- **[70]** [/en-us/graph/tutorial-accessreviews-securitygroup](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup) — Tutorial Accessreviews Securitygroup
- **[70]** [/en-us/graph/tutorial-entra-internet-access](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access) — Tutorial Entra Internet Access
- **[70]** [/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver) — Tutorial Lifecycle Workflows Scheduled Leaver
- **[60]** [/en-us/azure/azure-web-pubsub/tutorial-serverless-notification](https://learn.microsoft.com/en-us/azure/azure-web-pubsub/tutorial-serverless-notification) — Tutorial Serverless Notification
- **[60]** [/en-us/graph/api/application-list](https://learn.microsoft.com/en-us/graph/api/application-list) — Application List
- **[60]** [/en-us/graph/api/approvalitem-cancel](https://learn.microsoft.com/en-us/graph/api/approvalitem-cancel) — Approvalitem Cancel
- **[60]** [/en-us/graph/api/attachment-get](https://learn.microsoft.com/en-us/graph/api/attachment-get) — Attachment Get
- **[60]** [/en-us/graph/api/authentication-get](https://learn.microsoft.com/en-us/graph/api/authentication-get) — Authentication Get
- **[60]** [/en-us/graph/api/authenticationmethod-resetpassword](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword) — Authenticationmethod Resetpassword
- **[60]** [/en-us/graph/api/callrecords-callrecord-get](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get) — Callrecords Callrecord Get
- **[60]** [/en-us/graph/api/callrecords-cloudcommunications-list-callrecords](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords) — Callrecords Cloudcommunications List Callrecords
- **[60]** [/en-us/graph/api/cloudpc-get](https://learn.microsoft.com/en-us/graph/api/cloudpc-get) — Cloudpc Get
- **[60]** [/en-us/graph/api/cloudpc-reprovision](https://learn.microsoft.com/en-us/graph/api/cloudpc-reprovision) — Cloudpc Reprovision
- **[60]** [/en-us/graph/api/cloudpc-restore](https://learn.microsoft.com/en-us/graph/api/cloudpc-restore) — Cloudpc Restore
- **[60]** [/en-us/graph/api/cloudpc-troubleshoot](https://learn.microsoft.com/en-us/graph/api/cloudpc-troubleshoot) — Cloudpc Troubleshoot
- **[60]** [/en-us/graph/api/columndefinition-delete](https://learn.microsoft.com/en-us/graph/api/columndefinition-delete) — Columndefinition Delete
- **[60]** [/en-us/graph/api/conditionalaccesspolicy-get](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get) — Conditionalaccesspolicy Get
- **[60]** [/en-us/graph/api/configurationmonitor-update](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update) — Configurationmonitor Update
- **[60]** [/en-us/graph/api/identityapiconnector-create](https://learn.microsoft.com/en-us/graph/api/identityapiconnector-create) — Identityapiconnector Create
- **[60]** [/en-us/graph/api/intune-apps-win32lobapp-update](https://learn.microsoft.com/en-us/graph/api/intune-apps-win32lobapp-update) — Intune Apps Win32Lobapp Update
- **[60]** [/en-us/graph/api/intune-cloudpkigraphservice-cloudcertificationauthority-list](https://learn.microsoft.com/en-us/graph/api/intune-cloudpkigraphservice-cloudcertificationauthority-list) — Intune Cloudpkigraphservice Cloudcertificationauthority List
- **[60]** [/en-us/graph/api/intune-cloudpkigraphservice-cloudcertificationauthorityleafcertificate-list](https://learn.microsoft.com/en-us/graph/api/intune-cloudpkigraphservice-cloudcertificationauthorityleafcertificate-list) — Intune Cloudpkigraphservice Cloudcertificationauthorityleafcertificate List
- **[60]** [/en-us/graph/api/intune-enrollment-importedwindowsautopilotdeviceidentity-create](https://learn.microsoft.com/en-us/graph/api/intune-enrollment-importedwindowsautopilotdeviceidentity-create) — Intune Enrollment Importedwindowsautopilotdeviceidentity Create
- **[60]** [/en-us/graph/api/itemactivity-getbyinterval](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval) — Itemactivity Getbyinterval
- **[60]** [/en-us/graph/api/listitem-delta](https://learn.microsoft.com/en-us/graph/api/listitem-delta) — Listitem Delta
- **[60]** [/en-us/graph/api/meetingregistrant-delete](https://learn.microsoft.com/en-us/graph/api/meetingregistrant-delete) — Meetingregistrant Delete
- **[60]** [/en-us/graph/api/onlinemeeting-list-recordings](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-recordings) — Onlinemeeting List Recordings
- **[60]** [/en-us/graph/api/onlinemeeting-list-transcripts](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts) — Onlinemeeting List Transcripts
- **[60]** [/en-us/graph/api/pagetemplate-get](https://learn.microsoft.com/en-us/graph/api/pagetemplate-get) — Pagetemplate Get
- **[60]** [/en-us/graph/api/partners-billing-billedreconciliation-export](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedreconciliation-export) — Partners Billing Billedreconciliation Export
- **[60]** [/en-us/graph/api/partners-billing-billedusage-export](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export) — Partners Billing Billedusage Export
- **[60]** [/en-us/graph/api/partners-billing-unbilledreconciliation-export](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export) — Partners Billing Unbilledreconciliation Export
- **[60]** [/en-us/graph/api/regionalandlanguagesettings-get](https://learn.microsoft.com/en-us/graph/api/regionalandlanguagesettings-get) — Regionalandlanguagesettings Get
- **[60]** [/en-us/graph/api/reportsroot-list-readingassignmentsubmissions](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions) — Reportsroot List Readingassignmentsubmissions
- **[60]** [/en-us/graph/api/reportsroot-list-reflectcheckinresponses](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses) — Reportsroot List Reflectcheckinresponses
- **[60]** [/en-us/graph/api/resources/basicauthentication](https://learn.microsoft.com/en-us/graph/api/resources/basicauthentication) — Basicauthentication
- **[60]** [/en-us/graph/api/resources/checklistitem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem) — Checklistitem
- **[60]** [/en-us/graph/api/resources/cloudpcsnapshotimportactionresult](https://learn.microsoft.com/en-us/graph/api/resources/cloudpcsnapshotimportactionresult) — Cloudpcsnapshotimportactionresult
- **[60]** [/en-us/graph/api/resources/communications-api-overview](https://learn.microsoft.com/en-us/graph/api/resources/communications-api-overview) — Communications Api Overview
- **[60]** [/en-us/graph/api/resources/customclaimspolicy](https://learn.microsoft.com/en-us/graph/api/resources/customclaimspolicy) — Customclaimspolicy
- **[60]** [/en-us/graph/api/resources/delegatedadminrelationships-api-overview](https://learn.microsoft.com/en-us/graph/api/resources/delegatedadminrelationships-api-overview) — Delegatedadminrelationships Api Overview
- **[60]** [/en-us/graph/api/resources/employeeexperience](https://learn.microsoft.com/en-us/graph/api/resources/employeeexperience) — Employeeexperience
- **[60]** [/en-us/graph/api/resources/federatedidentitycredentials-overview](https://learn.microsoft.com/en-us/graph/api/resources/federatedidentitycredentials-overview) — Federatedidentitycredentials Overview
- **[60]** [/en-us/graph/api/resources/itemreference](https://learn.microsoft.com/en-us/graph/api/resources/itemreference) — Itemreference
- **[60]** [/en-us/graph/api/resources/learningcourseactivity](https://learn.microsoft.com/en-us/graph/api/resources/learningcourseactivity) — Learningcourseactivity
- **[60]** [/en-us/graph/api/resources/linkedresource](https://learn.microsoft.com/en-us/graph/api/resources/linkedresource) — Linkedresource
- **[60]** [/en-us/graph/api/resources/oidcclientsecretauthentication](https://learn.microsoft.com/en-us/graph/api/resources/oidcclientsecretauthentication) — Oidcclientsecretauthentication
- **[60]** [/en-us/graph/api/resources/partners-billing-api-overview](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-api-overview) — Partners Billing Api Overview
- **[60]** [/en-us/graph/api/resources/passwordprofile](https://learn.microsoft.com/en-us/graph/api/resources/passwordprofile) — Passwordprofile
- **[60]** [/en-us/graph/api/resources/permission](https://learn.microsoft.com/en-us/graph/api/resources/permission) — Permission
- **[60]** [/en-us/graph/api/resources/phoneauthenticationmethod](https://learn.microsoft.com/en-us/graph/api/resources/phoneauthenticationmethod) — Phoneauthenticationmethod
- **[60]** [/en-us/graph/api/resources/reflectcheckinresponse](https://learn.microsoft.com/en-us/graph/api/resources/reflectcheckinresponse) — Reflectcheckinresponse
- **[60]** [/en-us/graph/api/resources/sharinglink](https://learn.microsoft.com/en-us/graph/api/resources/sharinglink) — Sharinglink
- **[60]** [/en-us/graph/api/resources/subscribedsku](https://learn.microsoft.com/en-us/graph/api/resources/subscribedsku) — Subscribedsku
- **[60]** [/en-us/graph/api/resources/targetpolicyendpoints](https://learn.microsoft.com/en-us/graph/api/resources/targetpolicyendpoints) — Targetpolicyendpoints
- **[60]** [/en-us/graph/api/resources/user](https://learn.microsoft.com/en-us/graph/api/resources/user) — User
- **[60]** [/en-us/graph/api/resources/webauthnauthenticatorselectioncriteria](https://learn.microsoft.com/en-us/graph/api/resources/webauthnauthenticatorselectioncriteria) — Webauthnauthenticatorselectioncriteria
- **[60]** [/en-us/graph/api/synchronization-serviceprincipal-put-synchronization](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization) — Synchronization Serviceprincipal Put Synchronization
- **[60]** [/en-us/graph/api/temporaryaccesspassauthenticationmethodconfiguration-get](https://learn.microsoft.com/en-us/graph/api/temporaryaccesspassauthenticationmethodconfiguration-get) — Temporaryaccesspassauthenticationmethodconfiguration Get
- **[60]** [/en-us/graph/api/user-get](https://learn.microsoft.com/en-us/graph/api/user-get) — User Get
- **[60]** [/en-us/graph/api/user-list-cloudpcs](https://learn.microsoft.com/en-us/graph/api/user-list-cloudpcs) — User List Cloudpcs
- **[60]** [/en-us/graph/api/user-post-contacts](https://learn.microsoft.com/en-us/graph/api/user-post-contacts) — User Post Contacts
- **[60]** [/en-us/graph/api/user-sendmail](https://learn.microsoft.com/en-us/graph/api/user-sendmail) — User Sendmail
- **[60]** [/en-us/graph/api/user-translateexchangeids](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids) — User Translateexchangeids
- **[60]** [/en-us/graph/api/useraccountinformation-get](https://learn.microsoft.com/en-us/graph/api/useraccountinformation-get) — Useraccountinformation Get
- **[60]** [/en-us/graph/application-saml-sso-configure-api](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api) — Application Saml Sso Configure Api
- **[60]** [/en-us/graph/applications-concept-overview](https://learn.microsoft.com/en-us/graph/applications-concept-overview) — Applications Concept Overview
- **[60]** [/en-us/graph/azuread-users-concept-overview](https://learn.microsoft.com/en-us/graph/azuread-users-concept-overview) — Azuread Users Concept Overview
- **[60]** [/en-us/graph/best-practices-graph-permission](https://learn.microsoft.com/en-us/graph/best-practices-graph-permission) — Best Practices Graph Permission

---

**Excluded from archive (50 pages dropped from preranked top-150):** /graph/toolkit (2), /azure/communication-services (2), /azure/api-management (2), /graph/booking-concept-overview (1), /graph/bookingsbusiness-business-rules (1), /graph/businessscenarios-concept-overview (1), /graph/cloud-communication-online-meeting-application-access-policy (1), /graph/cloud-communications-callrecords (1)
