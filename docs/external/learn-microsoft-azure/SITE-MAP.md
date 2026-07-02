# Microsoft Azure + Graph (API-connectivity / Outlook scope) — Site Cartography

Cartography of `learn.microsoft.com/en-us/azure/` + `/en-us/graph/` filtered to API-connectivity and Outlook surfaces. 100 of 100 selected pages archived locally as Markdown.

Scope: Microsoft Graph (Outlook mail, calendar, events), Microsoft identity platform / Entra ID, Azure API Management, Logic Apps Outlook connectors, Functions HTTP triggers, Communication Services email, Key Vault, webhook plumbing.

- Local markdown lives under [pages/](pages/) — paths mirror the URL structure (locale `/en-us/` stripped)
- `[online]` links point back to the original page on `learn.microsoft.com`
- Tier letters (S/A/B) reflect content importance — see [PAGE-GRADING.md](PAGE-GRADING.md)

---

### azure / api-management

- **[B]** [azure/api-management/api-management-howto-protect-backend-with-aad.md](pages/azure/api-management/api-management-howto-protect-backend-with-aad.md) — Protect an API in Azure API Management using OAuth 2.0 authorization with Microsoft Entra ID · [online](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-protect-backend-with-aad)
- **[B]** [azure/api-management/api-management-key-concepts.md](pages/azure/api-management/api-management-key-concepts.md) — What is Azure API Management? · [online](https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts)
- **[B]** [azure/api-management/api-management-subscriptions.md](pages/azure/api-management/api-management-subscriptions.md) — Subscriptions in Azure API Management · [online](https://learn.microsoft.com/en-us/azure/api-management/api-management-subscriptions)

### azure / azure-web-pubsub

- **[B]** [azure/azure-web-pubsub/tutorial-serverless-notification.md](pages/azure/azure-web-pubsub/tutorial-serverless-notification.md) — Tutorial: Create a serverless notification app with Azure Functions and Azure Web PubSub service · [online](https://learn.microsoft.com/en-us/azure/azure-web-pubsub/tutorial-serverless-notification)

### azure / communication-services

- **[A]** [azure/communication-services/concepts/email/email-overview.md](pages/azure/communication-services/concepts/email/email-overview.md) — Overview of Azure Communication Services email · [online](https://learn.microsoft.com/en-us/azure/communication-services/concepts/email/email-overview)

### graph / (root)

- **[B]** [graph/application-saml-sso-configure-api.md](pages/graph/application-saml-sso-configure-api.md) — Configure SAML-based single sign-on for your application using Microsoft Graph · [online](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api)
- **[B]** [graph/applications-concept-overview.md](pages/graph/applications-concept-overview.md) — Applications API overview · [online](https://learn.microsoft.com/en-us/graph/applications-concept-overview)
- **[S]** [graph/auth-v2-service.md](pages/graph/auth-v2-service.md) — Get access without a user · [online](https://learn.microsoft.com/en-us/graph/auth-v2-service)
- **[S]** [graph/auth-v2-user.md](pages/graph/auth-v2-user.md) — Get access on behalf of a user · [online](https://learn.microsoft.com/en-us/graph/auth-v2-user)
- **[B]** [graph/azuread-users-concept-overview.md](pages/graph/azuread-users-concept-overview.md) — Overview of users in Microsoft Graph · [online](https://learn.microsoft.com/en-us/graph/azuread-users-concept-overview)
- **[B]** [graph/best-practices-graph-permission.md](pages/graph/best-practices-graph-permission.md) — Best practices for using Microsoft Graph permissions · [online](https://learn.microsoft.com/en-us/graph/best-practices-graph-permission)
- **[S]** [graph/delta-query-groups.md](pages/graph/delta-query-groups.md) — Get incremental changes for groups · [online](https://learn.microsoft.com/en-us/graph/delta-query-groups)
- **[S]** [graph/delta-query-overview.md](pages/graph/delta-query-overview.md) — Use delta query to track changes in Microsoft Graph data · [online](https://learn.microsoft.com/en-us/graph/delta-query-overview)
- **[S]** [graph/outlook-calendar-online-meetings.md](pages/graph/outlook-calendar-online-meetings.md) — Create or set an event as an online meeting in an Outlook calendar · [online](https://learn.microsoft.com/en-us/graph/outlook-calendar-online-meetings)
- **[S]** [graph/outlook-get-mime-message.md](pages/graph/outlook-get-mime-message.md) — Get MIME content of a message · [online](https://learn.microsoft.com/en-us/graph/outlook-get-mime-message)
- **[S]** [graph/outlook-schedule-recurring-events.md](pages/graph/outlook-schedule-recurring-events.md) — Schedule repeating appointments as recurring events in Outlook · [online](https://learn.microsoft.com/en-us/graph/outlook-schedule-recurring-events)
- **[S]** [graph/overview.md](pages/graph/overview.md) — Overview of Microsoft Graph · [online](https://learn.microsoft.com/en-us/graph/overview)
- **[A]** [graph/permissions-reference.md](pages/graph/permissions-reference.md) — Microsoft Graph permissions reference · [online](https://learn.microsoft.com/en-us/graph/permissions-reference)
- **[B]** [graph/tutorial-accessreviews-securitygroup.md](pages/graph/tutorial-accessreviews-securitygroup.md) — Review access to security groups using access reviews APIs · [online](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup)
- **[B]** [graph/tutorial-entra-internet-access.md](pages/graph/tutorial-entra-internet-access.md) — Configure Microsoft Entra Internet Access using Microsoft Graph APIs · [online](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access)
- **[B]** [graph/tutorial-lifecycle-workflows-scheduled-leaver.md](pages/graph/tutorial-lifecycle-workflows-scheduled-leaver.md) — Automate employee offboarding tasks after their last day of work using Lifecycle Workflows APIs · [online](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver)
- **[A]** [graph/use-the-api.md](pages/graph/use-the-api.md) — Use the Microsoft Graph API · [online](https://learn.microsoft.com/en-us/graph/use-the-api)

### graph / api

- **[B]** [graph/api/application-list.md](pages/graph/api/application-list.md) — List applications · [online](https://learn.microsoft.com/en-us/graph/api/application-list)
- **[B]** [graph/api/approvalitem-cancel.md](pages/graph/api/approvalitem-cancel.md) — approvalItem: cancel · [online](https://learn.microsoft.com/en-us/graph/api/approvalitem-cancel)
- **[B]** [graph/api/attachment-get.md](pages/graph/api/attachment-get.md) — Get attachment · [online](https://learn.microsoft.com/en-us/graph/api/attachment-get)
- **[B]** [graph/api/authentication-get.md](pages/graph/api/authentication-get.md) — Get authentication method states · [online](https://learn.microsoft.com/en-us/graph/api/authentication-get)
- **[B]** [graph/api/authenticationmethod-resetpassword.md](pages/graph/api/authenticationmethod-resetpassword.md) — authenticationMethod: resetPassword · [online](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword)
- **[B]** [graph/api/callrecords-callrecord-get.md](pages/graph/api/callrecords-callrecord-get.md) — Get callRecord · [online](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get)
- **[B]** [graph/api/callrecords-cloudcommunications-list-callrecords.md](pages/graph/api/callrecords-cloudcommunications-list-callrecords.md) — List callRecords · [online](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords)
- **[B]** [graph/api/cloudpc-get.md](pages/graph/api/cloudpc-get.md) — Get cloudPC · [online](https://learn.microsoft.com/en-us/graph/api/cloudpc-get)
- **[B]** [graph/api/cloudpc-reprovision.md](pages/graph/api/cloudpc-reprovision.md) — cloudPC: reprovision · [online](https://learn.microsoft.com/en-us/graph/api/cloudpc-reprovision)
- **[B]** [graph/api/cloudpc-restore.md](pages/graph/api/cloudpc-restore.md) — cloudPC: restore · [online](https://learn.microsoft.com/en-us/graph/api/cloudpc-restore)
- **[B]** [graph/api/cloudpc-troubleshoot.md](pages/graph/api/cloudpc-troubleshoot.md) — cloudPC: troubleshoot · [online](https://learn.microsoft.com/en-us/graph/api/cloudpc-troubleshoot)
- **[B]** [graph/api/columndefinition-delete.md](pages/graph/api/columndefinition-delete.md) — Delete columnDefinition · [online](https://learn.microsoft.com/en-us/graph/api/columndefinition-delete)
- **[B]** [graph/api/conditionalaccesspolicy-get.md](pages/graph/api/conditionalaccesspolicy-get.md) — Get conditionalAccessPolicy · [online](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get)
- **[B]** [graph/api/configurationmonitor-update.md](pages/graph/api/configurationmonitor-update.md) — Update configurationMonitor · [online](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update)
- **[B]** [graph/api/identityapiconnector-create.md](pages/graph/api/identityapiconnector-create.md) — Create identityApiConnector · [online](https://learn.microsoft.com/en-us/graph/api/identityapiconnector-create)
- **[B]** [graph/api/intune-apps-win32lobapp-update.md](pages/graph/api/intune-apps-win32lobapp-update.md) — Update win32LobApp · [online](https://learn.microsoft.com/en-us/graph/api/intune-apps-win32lobapp-update)
- **[B]** [graph/api/intune-cloudpkigraphservice-cloudcertificationauthority-list.md](pages/graph/api/intune-cloudpkigraphservice-cloudcertificationauthority-list.md) — List cloudCertificationAuthorities · [online](https://learn.microsoft.com/en-us/graph/api/intune-cloudpkigraphservice-cloudcertificationauthority-list)
- **[B]** [graph/api/intune-cloudpkigraphservice-cloudcertificationauthorityleafcertificate-list.md](pages/graph/api/intune-cloudpkigraphservice-cloudcertificationauthorityleafcertificate-list.md) — List cloudCertificationAuthorityLeafCertificates · [online](https://learn.microsoft.com/en-us/graph/api/intune-cloudpkigraphservice-cloudcertificationauthorityleafcertificate-list)
- **[B]** [graph/api/intune-enrollment-importedwindowsautopilotdeviceidentity-create.md](pages/graph/api/intune-enrollment-importedwindowsautopilotdeviceidentity-create.md) — Create importedWindowsAutopilotDeviceIdentity · [online](https://learn.microsoft.com/en-us/graph/api/intune-enrollment-importedwindowsautopilotdeviceidentity-create)
- **[B]** [graph/api/itemactivity-getbyinterval.md](pages/graph/api/itemactivity-getbyinterval.md) — Get item activity stats by interval · [online](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval)
- **[B]** [graph/api/listitem-delta.md](pages/graph/api/listitem-delta.md) — listItem: delta · [online](https://learn.microsoft.com/en-us/graph/api/listitem-delta)
- **[B]** [graph/api/meetingregistrant-delete.md](pages/graph/api/meetingregistrant-delete.md) — Unenroll meeting registrant (deprecated) · [online](https://learn.microsoft.com/en-us/graph/api/meetingregistrant-delete)
- **[B]** [graph/api/onlinemeeting-list-recordings.md](pages/graph/api/onlinemeeting-list-recordings.md) — List recordings · [online](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-recordings)
- **[B]** [graph/api/onlinemeeting-list-transcripts.md](pages/graph/api/onlinemeeting-list-transcripts.md) — List transcripts · [online](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts)
- **[B]** [graph/api/overview.md](pages/graph/api/overview.md) — Microsoft Graph REST API v1.0 endpoint reference · [online](https://learn.microsoft.com/en-us/graph/api/overview)
- **[B]** [graph/api/pagetemplate-get.md](pages/graph/api/pagetemplate-get.md) — Get pageTemplate · [online](https://learn.microsoft.com/en-us/graph/api/pagetemplate-get)
- **[B]** [graph/api/partners-billing-billedreconciliation-export.md](pages/graph/api/partners-billing-billedreconciliation-export.md) — billedReconciliation: export · [online](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedreconciliation-export)
- **[B]** [graph/api/partners-billing-billedusage-export.md](pages/graph/api/partners-billing-billedusage-export.md) — billedUsage: export · [online](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export)
- **[B]** [graph/api/partners-billing-unbilledreconciliation-export.md](pages/graph/api/partners-billing-unbilledreconciliation-export.md) — unbilledReconciliation: export · [online](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export)
- **[B]** [graph/api/regionalandlanguagesettings-get.md](pages/graph/api/regionalandlanguagesettings-get.md) — Get regionalAndLanguageSettings · [online](https://learn.microsoft.com/en-us/graph/api/regionalandlanguagesettings-get)
- **[B]** [graph/api/reportsroot-list-readingassignmentsubmissions.md](pages/graph/api/reportsroot-list-readingassignmentsubmissions.md) — List readingAssignmentSubmissions · [online](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions)
- **[B]** [graph/api/reportsroot-list-reflectcheckinresponses.md](pages/graph/api/reportsroot-list-reflectcheckinresponses.md) — List reflectCheckInResponses · [online](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses)
- **[B]** [graph/api/resources/basicauthentication.md](pages/graph/api/resources/basicauthentication.md) — basicAuthentication resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/basicauthentication)
- **[A]** [graph/api/resources/calendar-overview.md](pages/graph/api/resources/calendar-overview.md) — Working with calendars and events using the Microsoft Graph API · [online](https://learn.microsoft.com/en-us/graph/api/resources/calendar-overview)
- **[B]** [graph/api/resources/checklistitem.md](pages/graph/api/resources/checklistitem.md) — checklistItem resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem)
- **[B]** [graph/api/resources/cloudpcsnapshotimportactionresult.md](pages/graph/api/resources/cloudpcsnapshotimportactionresult.md) — cloudPcSnapshotImportActionResult resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/cloudpcsnapshotimportactionresult)
- **[B]** [graph/api/resources/communications-api-overview.md](pages/graph/api/resources/communications-api-overview.md) — Working with the cloud communications API in Microsoft Graph · [online](https://learn.microsoft.com/en-us/graph/api/resources/communications-api-overview)
- **[B]** [graph/api/resources/customclaimspolicy.md](pages/graph/api/resources/customclaimspolicy.md) — customClaimsPolicy resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/customclaimspolicy)
- **[B]** [graph/api/resources/delegatedadminrelationships-api-overview.md](pages/graph/api/resources/delegatedadminrelationships-api-overview.md) — Granular delegated admin privileges (GDAP) API overview · [online](https://learn.microsoft.com/en-us/graph/api/resources/delegatedadminrelationships-api-overview)
- **[B]** [graph/api/resources/employeeexperience.md](pages/graph/api/resources/employeeexperience.md) — employeeExperience resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/employeeexperience)
- **[A]** [graph/api/resources/event.md](pages/graph/api/resources/event.md) — event resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/event)
- **[B]** [graph/api/resources/federatedidentitycredentials-overview.md](pages/graph/api/resources/federatedidentitycredentials-overview.md) — Overview of federated identity credentials in Microsoft Entra ID · [online](https://learn.microsoft.com/en-us/graph/api/resources/federatedidentitycredentials-overview)
- **[B]** [graph/api/resources/itemreference.md](pages/graph/api/resources/itemreference.md) — itemReference resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/itemreference)
- **[B]** [graph/api/resources/learningcourseactivity.md](pages/graph/api/resources/learningcourseactivity.md) — learningCourseActivity resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/learningcourseactivity)
- **[B]** [graph/api/resources/linkedresource.md](pages/graph/api/resources/linkedresource.md) — linkedResource resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/linkedresource)
- **[A]** [graph/api/resources/mail-api-overview.md](pages/graph/api/resources/mail-api-overview.md) — Use the Outlook mail REST API · [online](https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview)
- **[A]** [graph/api/resources/mailfolder.md](pages/graph/api/resources/mailfolder.md) — mailFolder resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder)
- **[A]** [graph/api/resources/message.md](pages/graph/api/resources/message.md) — message resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/message)
- **[B]** [graph/api/resources/oidcclientsecretauthentication.md](pages/graph/api/resources/oidcclientsecretauthentication.md) — oidcClientSecretAuthentication resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/oidcclientsecretauthentication)
- **[B]** [graph/api/resources/partners-billing-api-overview.md](pages/graph/api/resources/partners-billing-api-overview.md) — Use the Microsoft Graph API to export partner billing data · [online](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-api-overview)
- **[B]** [graph/api/resources/passwordprofile.md](pages/graph/api/resources/passwordprofile.md) — passwordProfile resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/passwordprofile)
- **[B]** [graph/api/resources/permission.md](pages/graph/api/resources/permission.md) — Permission resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/permission)
- **[B]** [graph/api/resources/phoneauthenticationmethod.md](pages/graph/api/resources/phoneauthenticationmethod.md) — phoneAuthenticationMethod resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/phoneauthenticationmethod)
- **[B]** [graph/api/resources/reflectcheckinresponse.md](pages/graph/api/resources/reflectcheckinresponse.md) — reflectCheckInResponse resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/reflectcheckinresponse)
- **[B]** [graph/api/resources/sharinglink.md](pages/graph/api/resources/sharinglink.md) — sharingLink resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/sharinglink)
- **[B]** [graph/api/resources/subscribedsku.md](pages/graph/api/resources/subscribedsku.md) — subscribedSku resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/subscribedsku)
- **[B]** [graph/api/resources/targetpolicyendpoints.md](pages/graph/api/resources/targetpolicyendpoints.md) — targetPolicyEndpoints resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/targetpolicyendpoints)
- **[B]** [graph/api/resources/user.md](pages/graph/api/resources/user.md) — user resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/user)
- **[B]** [graph/api/resources/webauthnauthenticatorselectioncriteria.md](pages/graph/api/resources/webauthnauthenticatorselectioncriteria.md) — webauthnAuthenticatorSelectionCriteria resource type · [online](https://learn.microsoft.com/en-us/graph/api/resources/webauthnauthenticatorselectioncriteria)
- **[B]** [graph/api/synchronization-serviceprincipal-put-synchronization.md](pages/graph/api/synchronization-serviceprincipal-put-synchronization.md) — Add synchronization secrets · [online](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization)
- **[B]** [graph/api/temporaryaccesspassauthenticationmethodconfiguration-get.md](pages/graph/api/temporaryaccesspassauthenticationmethodconfiguration-get.md) — Get temporaryAccessPassAuthenticationMethodConfiguration · [online](https://learn.microsoft.com/en-us/graph/api/temporaryaccesspassauthenticationmethodconfiguration-get)
- **[B]** [graph/api/user-get.md](pages/graph/api/user-get.md) — Get a user · [online](https://learn.microsoft.com/en-us/graph/api/user-get)
- **[B]** [graph/api/user-list-cloudpcs.md](pages/graph/api/user-list-cloudpcs.md) — List cloudPCs for user · [online](https://learn.microsoft.com/en-us/graph/api/user-list-cloudpcs)
- **[B]** [graph/api/user-post-contacts.md](pages/graph/api/user-post-contacts.md) — Create contact · [online](https://learn.microsoft.com/en-us/graph/api/user-post-contacts)
- **[B]** [graph/api/user-sendmail.md](pages/graph/api/user-sendmail.md) — user: sendMail · [online](https://learn.microsoft.com/en-us/graph/api/user-sendmail)
- **[B]** [graph/api/user-translateexchangeids.md](pages/graph/api/user-translateexchangeids.md) — user: translateExchangeIds · [online](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids)
- **[B]** [graph/api/useraccountinformation-get.md](pages/graph/api/useraccountinformation-get.md) — Get userAccountInformation · [online](https://learn.microsoft.com/en-us/graph/api/useraccountinformation-get)

### graph / auth

- **[S]** [graph/auth/auth-concepts.md](pages/graph/auth/auth-concepts.md) — Authentication and authorization basics · [online](https://learn.microsoft.com/en-us/graph/auth/auth-concepts)

### graph / mcp-server

- **[B]** [graph/mcp-server/overview.md](pages/graph/mcp-server/overview.md) — Overview of Microsoft MCP Server for Enterprise (preview) · [online](https://learn.microsoft.com/en-us/graph/mcp-server/overview)

### graph / sdks

- **[A]** [graph/sdks/choose-authentication-providers.md](pages/graph/sdks/choose-authentication-providers.md) — Choose a Microsoft Graph authentication provider based on the scenario · [online](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers)
- **[A]** [graph/sdks/national-clouds.md](pages/graph/sdks/national-clouds.md) — Access national cloud deployments with the Microsoft Graph SDKs · [online](https://learn.microsoft.com/en-us/graph/sdks/national-clouds)

### graph / templates

- **[B]** [graph/templates/terraform/overview-terraform-for-graph.md](pages/graph/templates/terraform/overview-terraform-for-graph.md) — Terraform for Microsoft Graph resources · [online](https://learn.microsoft.com/en-us/graph/templates/terraform/overview-terraform-for-graph)

### graph / tutorials

- **[S]** [graph/tutorials/azure-functions__tutorial-step-3.md](pages/graph/tutorials/azure-functions__tutorial-step-3.md) — Microsoft Graph sample Azure Function · [online](https://learn.microsoft.com/en-us/graph/tutorials/azure-functions?tutorial-step=3)
- **[S]** [graph/tutorials/bot-framework__tutorial-step-2.md](pages/graph/tutorials/bot-framework__tutorial-step-2.md) — Microsoft Graph Bot Framework sample · [online](https://learn.microsoft.com/en-us/graph/tutorials/bot-framework?tutorial-step=2)
- **[S]** [graph/tutorials/php-email.md](pages/graph/tutorials/php-email.md) — Add email capabilities to PHP apps using Microsoft Graph · [online](https://learn.microsoft.com/en-us/graph/tutorials/php-email)
- **[S]** [graph/tutorials/python-email.md](pages/graph/tutorials/python-email.md) — Add email capabilities to Python apps using Microsoft Graph · [online](https://learn.microsoft.com/en-us/graph/tutorials/python-email)
- **[S]** [graph/tutorials/typescript-authentication.md](pages/graph/tutorials/typescript-authentication.md) — Add user authentication to TypeScript apps for Microsoft Graph · [online](https://learn.microsoft.com/en-us/graph/tutorials/typescript-authentication)
- **[S]** [graph/tutorials/uwp.md](pages/graph/tutorials/uwp.md) — Microsoft Graph sample UWP app · [online](https://learn.microsoft.com/en-us/graph/tutorials/uwp)

