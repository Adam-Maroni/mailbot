# user resource type

Namespace: microsoft.graph

Represents a Microsoft Entra user account. This resource is an open type that allows additional properties beyond those documented here. Inherits from [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0). Only [a subset of user properties are returned by default in v1.0](https://learn.microsoft.com/en-us/graph/api/resources/users?view=graph-rest-1.0#common-properties). To retrieve other properties, you must specify them in a `$select` query option.

This resource supports:

- Adding your own data to custom properties as [extensions](https://learn.microsoft.com/en-us/graph/extensibility-overview).
- Subscribing to [change notifications](https://learn.microsoft.com/en-us/graph/change-notifications-overview).
- Using [delta query](https://learn.microsoft.com/en-us/graph/delta-query-overview) to track incremental additions, deletions, and updates, by providing a [delta](https://learn.microsoft.com/en-us/graph/api/user-delta?view=graph-rest-1.0) function.

## Methods

| Method | Return Type | Description |
| --- | --- | --- |
| [List](https://learn.microsoft.com/en-us/graph/api/user-list?view=graph-rest-1.0) | [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) collection | Get a list of user objects. |
| [Create](https://learn.microsoft.com/en-us/graph/api/user-post-users?view=graph-rest-1.0) | [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) | Create a new user object. |
| [Get](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0) | [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) | Read properties and relationships of user object. |
| [Update](https://learn.microsoft.com/en-us/graph/api/user-update?view=graph-rest-1.0) | [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) | Update user object. |
| [Delete](https://learn.microsoft.com/en-us/graph/api/user-delete?view=graph-rest-1.0) | None | Delete user object. |
| [Get delta](https://learn.microsoft.com/en-us/graph/api/user-delta?view=graph-rest-1.0) | [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) collection | Get incremental changes for users. |
| [Change password](https://learn.microsoft.com/en-us/graph/api/user-changepassword?view=graph-rest-1.0) | None | Update your own password. |
| [Retry service provisioning](https://learn.microsoft.com/en-us/graph/api/user-retryserviceprovisioning?view=graph-rest-1.0) | None | Retry the user service provisioning. |
| [Revoke sign-in sessions](https://learn.microsoft.com/en-us/graph/api/user-revokesigninsessions?view=graph-rest-1.0) | None | Revokes all the user's refresh and session tokens issued to applications, by resetting the **signInSessionsValidFromDateTime** user property to the current date-time. It forces the user to sign in to those applications again. |
| [Export personal data](https://learn.microsoft.com/en-us/graph/api/user-exportpersonaldata?view=graph-rest-1.0) | None | Submits a data policy operation request, made by a company administrator to export an organizational user's data. |
| **App role assignments** |  |  |
| [List](https://learn.microsoft.com/en-us/graph/api/user-list-approleassignments?view=graph-rest-1.0) | [appRoleAssignment](https://learn.microsoft.com/en-us/graph/api/resources/approleassignment?view=graph-rest-1.0) collection | Get the apps and app roles assigned to this user. |
| [Add](https://learn.microsoft.com/en-us/graph/api/user-post-approleassignments?view=graph-rest-1.0) | [appRoleAssignment](https://learn.microsoft.com/en-us/graph/api/resources/approleassignment?view=graph-rest-1.0) | Assign an app role to this user. |
| [Remove](https://learn.microsoft.com/en-us/graph/api/user-delete-approleassignments?view=graph-rest-1.0) | None | Remove an app role assignment from this user. |
| **Calendar** |  |  |
| [List calendars](https://learn.microsoft.com/en-us/graph/api/user-list-calendars?view=graph-rest-1.0) | [calendar](https://learn.microsoft.com/en-us/graph/api/resources/calendar?view=graph-rest-1.0) collection | Get a Calendar object collection. |
| [Create calendar](https://learn.microsoft.com/en-us/graph/api/user-post-calendars?view=graph-rest-1.0) | [Calendar](https://learn.microsoft.com/en-us/graph/api/resources/calendar?view=graph-rest-1.0) | Create a new Calendar by posting to the calendars collection. |
| [List calendar groups](https://learn.microsoft.com/en-us/graph/api/user-list-calendargroups?view=graph-rest-1.0) | [calendarGroup](https://learn.microsoft.com/en-us/graph/api/resources/calendargroup?view=graph-rest-1.0) collection | Get a CalendarGroup object collection. |
| [Create calendar group](https://learn.microsoft.com/en-us/graph/api/user-post-calendargroups?view=graph-rest-1.0) | [CalendarGroup](https://learn.microsoft.com/en-us/graph/api/resources/calendargroup?view=graph-rest-1.0) | Create a new CalendarGroup by posting to the calendarGroups collection. |
| [List events](https://learn.microsoft.com/en-us/graph/api/user-list-events?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) collection | Get a list of event objects in the user's mailbox. The list contains single instance meetings and series masters. |
| [Create event](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) | Create a new event by posting to the events collection. |
| [Find meeting times](https://learn.microsoft.com/en-us/graph/api/user-findmeetingtimes?view=graph-rest-1.0) | [meetingTimeSuggestionsResult](https://learn.microsoft.com/en-us/graph/api/resources/meetingtimesuggestionsresult?view=graph-rest-1.0) | Find time and locations to meet based on attendee availability, location, or time constraints. |
| [Get free/busy schedule](https://learn.microsoft.com/en-us/graph/api/calendar-getschedule?view=graph-rest-1.0) | [scheduleInformation](https://learn.microsoft.com/en-us/graph/api/resources/scheduleinformation?view=graph-rest-1.0) | Get the free/busy availability information for a collection of users, distributions lists, or resources (rooms or equipment) for a specified period. |
| [List calendar view](https://learn.microsoft.com/en-us/graph/api/user-list-calendarview?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) collection | Get an event object collection. |
| [Reminder view](https://learn.microsoft.com/en-us/graph/api/user-reminderview?view=graph-rest-1.0) | [Reminder](https://learn.microsoft.com/en-us/graph/api/resources/reminder?view=graph-rest-1.0) collection | Return a list of calendar reminders within the start and end times specified. |
| **Cloud PC** |  |  |
| [List Cloud PCs](https://learn.microsoft.com/en-us/graph/api/user-list-cloudpcs?view=graph-rest-1.0) | [cloudPC](https://learn.microsoft.com/en-us/graph/api/resources/cloudpc?view=graph-rest-1.0) collection | List the [cloudPC](https://learn.microsoft.com/en-us/graph/api/resources/cloudpc?view=graph-rest-1.0) devices that are attributed to the signed-in user. |
| **Data security and governance** |  |  |
| [Compute protection scopes](https://learn.microsoft.com/en-us/graph/api/userprotectionscopecontainer-compute?view=graph-rest-1.0) | [policyUserScope](https://learn.microsoft.com/en-us/graph/api/resources/policyuserscope?view=graph-rest-1.0) collection | Compute the protection scopes for the signed-in user. |
| [Create content activity](https://learn.microsoft.com/en-us/graph/api/activitiescontainer-post-contentactivities?view=graph-rest-1.0) | [contentActivity](https://learn.microsoft.com/en-us/graph/api/resources/contentactivity?view=graph-rest-1.0) | Create a content activity for the signed-in user. |
| [Process content](https://learn.microsoft.com/en-us/graph/api/userdatasecurityandgovernance-processcontent?view=graph-rest-1.0) | [processContentResponse](https://learn.microsoft.com/en-us/graph/api/resources/processcontentresponse?view=graph-rest-1.0) | Process content against data protection policies in the context of the signed-in user. |
| **Delegated permission grants** |  |  |
| [List delegated permission grants](https://learn.microsoft.com/en-us/graph/api/user-list-oauth2permissiongrants?view=graph-rest-1.0) | [oAuth2PermissionGrant](https://learn.microsoft.com/en-us/graph/api/resources/oauth2permissiongrant?view=graph-rest-1.0) collection | Retrieve a list of delegated permissions granted to enable a client application to access an API on behalf of the user. |
| **Directory objects** |  |  |
| [Get by IDs](https://learn.microsoft.com/en-us/graph/api/directoryobject-getbyids?view=graph-rest-1.0) | String collection | Returns the directory objects specified in a list of IDs. |
| [Get delta for directory object](https://learn.microsoft.com/en-us/graph/api/directoryobject-delta?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Get incremental changes for directory objects such as [users](https://learn.microsoft.com/en-us/graph/api/user-delta?view=graph-rest-1.0), [groups](https://learn.microsoft.com/en-us/graph/api/group-delta?view=graph-rest-1.0), [applications](https://learn.microsoft.com/en-us/graph/api/application-delta?view=graph-rest-1.0), and [service principals](https://learn.microsoft.com/en-us/graph/api/serviceprincipal-delta?view=graph-rest-1.0). Filtering is required on either the **id** of the derived type or the derived type itself. For more information on delta queries, see the [Use delta query to track changes in Microsoft Graph data](https://learn.microsoft.com/en-us/graph/delta-query-overview). |
| [Check member groups](https://learn.microsoft.com/en-us/graph/api/directoryobject-checkmembergroups?view=graph-rest-1.0) | String collection | Check for membership in a list of groups. The check is transitive. |
| [Get member groups](https://learn.microsoft.com/en-us/graph/api/directoryobject-getmembergroups?view=graph-rest-1.0) | String collection | Return all the groups that the user is a member of. The check is transitive. |
| [Check member objects](https://learn.microsoft.com/en-us/graph/api/directoryobject-checkmemberobjects?view=graph-rest-1.0) | String collection | Check for membership in a list of group, directory role, or administrative unit objects. The function is transitive. |
| [Get member objects](https://learn.microsoft.com/en-us/graph/api/directoryobject-getmemberobjects?view=graph-rest-1.0) | String collection | Return all of the groups, administrative units, and directory roles that the user is a member of. The check is transitive. |
| [List created objects](https://learn.microsoft.com/en-us/graph/api/user-list-createdobjects?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Get the directory objects created by the user from the createdObjects navigation property. |
| [List owned devices](https://learn.microsoft.com/en-us/graph/api/user-list-owneddevices?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Get the devices that the user owns from the ownedDevices navigation property. |
| [List owned objects](https://learn.microsoft.com/en-us/graph/api/user-list-ownedobjects?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Get the directory objects owned by the user from the ownedObjects navigation property. |
| [List deleted groups owned by user](https://learn.microsoft.com/en-us/graph/api/directory-deleteditems-getuserownedobjects?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Retrieve the groups deleted in the tenant in the last 30 days and that owned by a user. |
| [List registered devices](https://learn.microsoft.com/en-us/graph/api/user-list-registereddevices?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Get the devices that are registered for the user from the registeredDevices navigation property. |
| [List deleted items](https://learn.microsoft.com/en-us/graph/api/directory-deleteditems-list?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Retrieve the users deleted in the tenant in the last 30 days. |
| [Get deleted item](https://learn.microsoft.com/en-us/graph/api/directory-deleteditems-get?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Retrieve a deleted user by ID. |
| [Restore deleted item](https://learn.microsoft.com/en-us/graph/api/directory-deleteditems-restore?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Restore a user deleted in the tenant in the last 30 days. |
| [Permanently delete item](https://learn.microsoft.com/en-us/graph/api/directory-deleteditems-delete?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Permanently delete a deleted user from the tenant. |
| **Drive** |  |  |
| [Get drive](https://learn.microsoft.com/en-us/graph/api/drive-get?view=graph-rest-1.0) | [drive](https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0) | Retrieve the properties and relationships of a Drive resource. |
| [List children](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0) | [DriveItems](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0) | Return a collection of DriveItems in the children relationship of a DriveItem. |
| **Employee experience** |  |  |
| [List assigned roles](https://learn.microsoft.com/en-us/graph/api/employeeexperienceuser-list-assignedroles?view=graph-rest-1.0) | [engagementRole](https://learn.microsoft.com/en-us/graph/api/resources/engagementrole?view=graph-rest-1.0) collection | Get a list of all the [roles](https://learn.microsoft.com/en-us/graph/api/resources/engagementrole?view=graph-rest-1.0) assigned to a user in Viva Engage. |
| **Groups** |  |  |
| [List joined teams](https://learn.microsoft.com/en-us/graph/api/user-list-joinedteams?view=graph-rest-1.0) | [team](https://learn.microsoft.com/en-us/graph/api/resources/team?view=graph-rest-1.0) collection | Get the Microsoft Teams teams that the user is a direct member of from the joinedTeams navigation property. |
| [List member of](https://learn.microsoft.com/en-us/graph/api/user-list-memberof?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Get the groups, directory roles, and administrative units that the user is a direct member of. This operation isn't transitive. |
| [List transitive member of](https://learn.microsoft.com/en-us/graph/api/user-list-transitivememberof?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Get the groups, directory roles, and administrative units that the user is a member of through either direct or transitive membership. |
| **Insights** |  |  |
| [List trending](https://learn.microsoft.com/en-us/graph/api/insights-list-trending?view=graph-rest-1.0) | [trending](https://learn.microsoft.com/en-us/graph/api/resources/insights-trending?view=graph-rest-1.0) collection | Get a list of trending files. |
| [Get content discovery settings](https://learn.microsoft.com/en-us/graph/api/usersettings-get?view=graph-rest-1.0) | [userSettings](https://learn.microsoft.com/en-us/graph/api/resources/usersettings?view=graph-rest-1.0) | Get users's content discovery settings. |
| [Update content discovery settings](https://learn.microsoft.com/en-us/graph/api/usersettings-update?view=graph-rest-1.0) | None | Update users's content discovery settings. |
| [List shared (deprecated)](https://learn.microsoft.com/en-us/graph/api/insights-list-shared?view=graph-rest-1.0) | [sharedInsight](https://learn.microsoft.com/en-us/graph/api/resources/insights-shared?view=graph-rest-1.0) collection | Get a list of shared files. This API is deprecated and will stop returning data after November 2026. |
| [List used (deprecated)](https://learn.microsoft.com/en-us/graph/api/insights-list-used?view=graph-rest-1.0) | [usedInsight](https://learn.microsoft.com/en-us/graph/api/resources/insights-used?view=graph-rest-1.0) collection | Get a list of used files. This API is deprecated and will stop returning data after November 2026. |
| **License management** |  |  |
| [Assign license](https://learn.microsoft.com/en-us/graph/api/user-assignlicense?view=graph-rest-1.0) | [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) | Add or remove subscriptions for the user. You can also enable and disable specific plans associated with a subscription. |
| [List license details](https://learn.microsoft.com/en-us/graph/api/user-list-licensedetails?view=graph-rest-1.0) | [licenseDetails](https://learn.microsoft.com/en-us/graph/api/resources/licensedetails?view=graph-rest-1.0) collection | Get a licenseDetails object collection. |
| [Reprocess license assignment](https://learn.microsoft.com/en-us/graph/api/user-reprocesslicenseassignment?view=graph-rest-1.0) | [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) | Reprocess subscription assignments for the user. |
| **Mail** |  |  |
| [List mail folders](https://learn.microsoft.com/en-us/graph/api/user-list-mailfolders?view=graph-rest-1.0) | [mailFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0) collection | Get the mail folder collection under the root folder of the signed-in user. |
| [Create mail folder](https://learn.microsoft.com/en-us/graph/api/user-post-mailfolders?view=graph-rest-1.0) | [mailFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0) | Create a new MailFolder by posting to the mailFolders collection. |
| [List messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) collection | Get all the messages in the signed-in user's mailbox. |
| [Create message](https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Create a new Message by posting to the messages collection. |
| [List overrides](https://learn.microsoft.com/en-us/graph/api/inferenceclassification-list-overrides?view=graph-rest-1.0) | [inferenceClassificationOverride](https://learn.microsoft.com/en-us/graph/api/resources/inferenceclassificationoverride?view=graph-rest-1.0) collection | Get the Focused Inbox overrides that a user configured to always classify messages from certain senders in specific ways. |
| [Create override](https://learn.microsoft.com/en-us/graph/api/inferenceclassification-post-overrides?view=graph-rest-1.0) | [inferenceClassificationOverride](https://learn.microsoft.com/en-us/graph/api/resources/inferenceclassificationoverride?view=graph-rest-1.0) | Create a Focused Inbox override for a sender identified by an SMTP address. |
| [List rules](https://learn.microsoft.com/en-us/graph/api/mailfolder-list-messagerules?view=graph-rest-1.0) | [messageRule](https://learn.microsoft.com/en-us/graph/api/resources/messagerule?view=graph-rest-1.0) collection | Get all the messageRule objects defined for the user's inbox. |
| [Create rule](https://learn.microsoft.com/en-us/graph/api/mailfolder-post-messagerules?view=graph-rest-1.0) | [messageRule](https://learn.microsoft.com/en-us/graph/api/resources/messagerule?view=graph-rest-1.0) | Create a messageRule object by specifying a set of conditions and actions. |
| [Send mail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0) | None | Send the message specified in the request body. |
| [Get mail tips](https://learn.microsoft.com/en-us/graph/api/user-getmailtips?view=graph-rest-1.0) | [mailTips](https://learn.microsoft.com/en-us/graph/api/resources/mailtips?view=graph-rest-1.0) collection | Return the MailTips of one or more recipients as available to the signed-in user. |
| **Notes** |  |  |
| [List notebooks](https://learn.microsoft.com/en-us/graph/api/onenote-list-notebooks?view=graph-rest-1.0) | [notebook](https://learn.microsoft.com/en-us/graph/api/resources/notebook?view=graph-rest-1.0) collection | Retrieve a list of notebook objects. |
| [Create notebook](https://learn.microsoft.com/en-us/graph/api/onenote-post-notebooks?view=graph-rest-1.0) | [notebook](https://learn.microsoft.com/en-us/graph/api/resources/notebook?view=graph-rest-1.0) | Create a new OneNote notebook. |
| **Org hierarchy** |  |  |
| [Assign manager](https://learn.microsoft.com/en-us/graph/api/user-post-manager?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) | Assign a user or an organizational contact as this user's manager. |
| [Get manager](https://learn.microsoft.com/en-us/graph/api/user-list-manager?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) | Get the user or organizational contact that is this user's manager from the manager navigation property. |
| [Remove manager](https://learn.microsoft.com/en-us/graph/api/user-delete-manager?view=graph-rest-1.0) | None | Remove the manager of a user. |
| [List direct reports](https://learn.microsoft.com/en-us/graph/api/user-list-directreports?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Get the users and contacts that report to the user from the directReports navigation property. |
| **Outlook settings** |  |  |
| [Get user mailbox settings](https://learn.microsoft.com/en-us/graph/api/user-get-mailboxsettings?view=graph-rest-1.0) | [mailboxSettings](https://learn.microsoft.com/en-us/graph/api/resources/mailboxsettings?view=graph-rest-1.0) | Get the user's mailboxSettings. |
| [Update user mailbox settings](https://learn.microsoft.com/en-us/graph/api/user-update-mailboxsettings?view=graph-rest-1.0) | [mailboxSettings](https://learn.microsoft.com/en-us/graph/api/resources/mailboxsettings?view=graph-rest-1.0) | Enable, configure, or disable one or more mailboxSettings for a user. |
| [List Outlook categories](https://learn.microsoft.com/en-us/graph/api/outlookuser-list-mastercategories?view=graph-rest-1.0) | [outlookCategory](https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory?view=graph-rest-1.0) collection | Get all the categories defined for the user. |
| [Create Outlook category](https://learn.microsoft.com/en-us/graph/api/outlookuser-post-mastercategories?view=graph-rest-1.0) | [outlookCategory](https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory?view=graph-rest-1.0) | Create an outlookCategory object in the user's master list of categories. |
| [Get supported languages](https://learn.microsoft.com/en-us/graph/api/outlookuser-supportedlanguages?view=graph-rest-1.0) | [localeInfo](https://learn.microsoft.com/en-us/graph/api/resources/localeinfo?view=graph-rest-1.0) collection | Get the list of locales and languages that are supported for the user, as configured on the user's mailbox server. |
| [Get supported time zones](https://learn.microsoft.com/en-us/graph/api/outlookuser-supportedtimezones?view=graph-rest-1.0) | [timeZoneInformation](https://learn.microsoft.com/en-us/graph/api/resources/timezoneinformation?view=graph-rest-1.0) collection | Get the list of time zones that are supported for the user, as configured on the user's mailbox server. |
| [Translate Exchange IDs](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0) | [convertIdResult](https://learn.microsoft.com/en-us/graph/api/resources/convertidresult?view=graph-rest-1.0) collection | Translate identifiers of Outlook-related resources between formats. |
| **People** |  |  |
| [List](https://learn.microsoft.com/en-us/graph/api/user-list-people?view=graph-rest-1.0) | [person](https://learn.microsoft.com/en-us/graph/api/resources/person?view=graph-rest-1.0) collection | Get a collection of person objects ordered by their relevance to the user. |
| **Personal contacts** |  |  |
| [List contacts](https://learn.microsoft.com/en-us/graph/api/user-list-contacts?view=graph-rest-1.0) | [contact](https://learn.microsoft.com/en-us/graph/api/resources/contact?view=graph-rest-1.0) collection | Get a contact collection from the default Contacts folder of the signed-in user. |
| [Create contact](https://learn.microsoft.com/en-us/graph/api/user-post-contacts?view=graph-rest-1.0) | [contact](https://learn.microsoft.com/en-us/graph/api/resources/contact?view=graph-rest-1.0) | Create a new Contact by posting to the contacts collection. |
| [List contact folders](https://learn.microsoft.com/en-us/graph/api/user-list-contactfolders?view=graph-rest-1.0) | [contactFolder](https://learn.microsoft.com/en-us/graph/api/resources/contactfolder?view=graph-rest-1.0) collection | Get the contact folder collection in the default Contacts folder of the signed-in user. |
| [Create contact folder](https://learn.microsoft.com/en-us/graph/api/user-post-contactfolders?view=graph-rest-1.0) | [contactFolder](https://learn.microsoft.com/en-us/graph/api/resources/contactfolder?view=graph-rest-1.0) | Create a new ContactFolder by posting to the contactFolders collection. |
| **Profile photo** |  |  |
| [Get](https://learn.microsoft.com/en-us/graph/api/profilephoto-get?view=graph-rest-1.0) | [profilePhoto](https://learn.microsoft.com/en-us/graph/api/resources/profilephoto?view=graph-rest-1.0) | Get the specified profilePhoto or its metadata (profilePhoto properties). |
| [Update](https://learn.microsoft.com/en-us/graph/api/profilephoto-update?view=graph-rest-1.0) | None | Update the photo for any user in the tenant including the signed-in user, or the specified group or contact. |
| [Delete](https://learn.microsoft.com/en-us/graph/api/profilephoto-delete?view=graph-rest-1.0) | None | Delete the photo for any user in the tenant including the signed-in user or the specified group. |
| **Planner** |  |  |
| [List tasks](https://learn.microsoft.com/en-us/graph/api/planneruser-list-tasks?view=graph-rest-1.0) | [plannerTask](https://learn.microsoft.com/en-us/graph/api/resources/plannertask?view=graph-rest-1.0) collection | Get plannerTasks assigned to the user. |
| **Sponsors** |  |  |
| [Assign](https://learn.microsoft.com/en-us/graph/api/user-post-sponsors?view=graph-rest-1.0) | None | Assign a user a sponsor. |
| [List](https://learn.microsoft.com/en-us/graph/api/user-list-sponsors?view=graph-rest-1.0) | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Get the users and groups who are this user's sponsors. |
| [Remove](https://learn.microsoft.com/en-us/graph/api/user-delete-sponsors?view=graph-rest-1.0) | None | Remove a user's sponsor. |
| **Teamwork** |  |  |
| [List associated teams](https://learn.microsoft.com/en-us/graph/api/associatedteaminfo-list?view=graph-rest-1.0) | [associatedTeamInfo](https://learn.microsoft.com/en-us/graph/api/resources/associatedteaminfo?view=graph-rest-1.0) collection | Get the list of teams in Microsoft Teams that a user is associated with. |
| [List apps installed for user](https://learn.microsoft.com/en-us/graph/api/userteamwork-list-installedapps?view=graph-rest-1.0) | [userScopeTeamsAppInstallation](https://learn.microsoft.com/en-us/graph/api/resources/userscopeteamsappinstallation?view=graph-rest-1.0) collection | Lists apps installed in the personal scope of a user. |
| [Gets the installed app for user](https://learn.microsoft.com/en-us/graph/api/userteamwork-get-installedapps?view=graph-rest-1.0) | [userScopeTeamsAppInstallation](https://learn.microsoft.com/en-us/graph/api/resources/userscopeteamsappinstallation?view=graph-rest-1.0) | Lists the specified app installed in the personal scope of a user. |
| [Add app for user](https://learn.microsoft.com/en-us/graph/api/userteamwork-post-installedapps?view=graph-rest-1.0) | None | Adds (installs) an app in the personal scope of a user. |
| [Remove app for user](https://learn.microsoft.com/en-us/graph/api/userteamwork-delete-installedapps?view=graph-rest-1.0) | None | Removes (uninstalls) an app in the personal scope of a user. |
| [Upgrade app installed for user](https://learn.microsoft.com/en-us/graph/api/userteamwork-teamsappinstallation-upgrade?view=graph-rest-1.0) | None | Upgrades to the latest version of the app installed in the personal scope of a user. |
| [Get chat between user and app](https://learn.microsoft.com/en-us/graph/api/userscopeteamsappinstallation-get-chat?view=graph-rest-1.0) | [Chat](https://learn.microsoft.com/en-us/graph/api/resources/chat?view=graph-rest-1.0) | Lists one-on-one chat between the user and the app. |
| [List permission grants](https://learn.microsoft.com/en-us/graph/api/user-list-permissiongrants?view=graph-rest-1.0) | [resourceSpecificPermissionGrant](https://learn.microsoft.com/en-us/graph/api/resources/resourcespecificpermissiongrant?view=graph-rest-1.0) collection | List all [resource-specific permission grants](https://learn.microsoft.com/en-us/graph/api/resources/resourcespecificpermissiongrant?view=graph-rest-1.0) of a [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0). |
| **Terms of use agreements** |  |  |
| [Agreement acceptances for a user](https://learn.microsoft.com/en-us/graph/api/user-list-agreementacceptances?view=graph-rest-1.0) | [agreementAcceptance](https://learn.microsoft.com/en-us/graph/api/resources/agreementacceptance?view=graph-rest-1.0) | Retrieve a user's agreementAcceptance objects. |
| **To-do tasks** |  |  |
| [List tasks](https://learn.microsoft.com/en-us/graph/api/todotasklist-list-tasks?view=graph-rest-1.0) | [todoTask](https://learn.microsoft.com/en-us/graph/api/resources/todotask?view=graph-rest-1.0) collection | Get all the [todoTask](https://learn.microsoft.com/en-us/graph/api/resources/todotask?view=graph-rest-1.0) resources in the specified list. |
| [Create task](https://learn.microsoft.com/en-us/graph/api/todotasklist-post-tasks?view=graph-rest-1.0) | [todoTask](https://learn.microsoft.com/en-us/graph/api/resources/todotask?view=graph-rest-1.0) | Create a [todoTask](https://learn.microsoft.com/en-us/graph/api/resources/todotask?view=graph-rest-1.0) in the specified task list. |
| [List task lists](https://learn.microsoft.com/en-us/graph/api/todo-list-lists?view=graph-rest-1.0) | [todoTaskList](https://learn.microsoft.com/en-us/graph/api/resources/todotasklist?view=graph-rest-1.0) collection | Get all the task lists in the user's mailbox. |
| [Create task list](https://learn.microsoft.com/en-us/graph/api/todo-post-lists?view=graph-rest-1.0) | [todoTaskList](https://learn.microsoft.com/en-us/graph/api/resources/todotasklist?view=graph-rest-1.0) | Create a To Do task list in the user's mailbox. |
| **User settings** |  |  |
| [Get](https://learn.microsoft.com/en-us/graph/api/usersettings-get?view=graph-rest-1.0) | [userSettings](https://learn.microsoft.com/en-us/graph/api/resources/usersettings?view=graph-rest-1.0) | Read the user and organization settings object. |
| [Update](https://learn.microsoft.com/en-us/graph/api/usersettings-update?view=graph-rest-1.0) | [userSettings](https://learn.microsoft.com/en-us/graph/api/resources/usersettings?view=graph-rest-1.0) | Update the properties of the settings object. |

## Properties

Important

Specific usage of `$filter` and the `$search` query parameter is supported only when you use the **ConsistencyLevel** header set to `eventual` and `$count`. For more information, see [Advanced query capabilities on directory objects](https://learn.microsoft.com/en-us/graph/aad-advanced-queries#user-properties).

| Property | Type | Description |
| --- | --- | --- |
| aboutMe | String | A freeform text entry field for the user to describe themselves. Requires `$select` to retrieve. |
| accountEnabled | Boolean | `true` if the account is enabled; otherwise, `false`. This property is required when a user is created. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, and `in`). |
| ageGroup | [ageGroup](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0#agegroup-values) | Sets the age group of the user. Allowed values: `null`, `Minor`, `NotAdult`, and `Adult`. For more information, see [legal age group property definitions](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0#legal-age-group-property-definitions). <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, and `in`). |
| assignedLicenses | [assignedLicense](https://learn.microsoft.com/en-us/graph/api/resources/assignedlicense?view=graph-rest-1.0) collection | The licenses that are assigned to the user, including inherited (group-based) licenses. This property doesn't differentiate between directly assigned and inherited licenses. Use the **licenseAssignmentStates** property to identify the directly assigned and inherited licenses. Not nullable. Requires `$select` to retrieve. Supports `$filter` (`eq`, `not`, `/$count eq 0`, `/$count ne 0`). |
| assignedPlans | [assignedPlan](https://learn.microsoft.com/en-us/graph/api/resources/assignedplan?view=graph-rest-1.0) collection | The plans that are assigned to the user. Read-only. Not nullable. <br>Requires `$select` to retrieve. Supports `$filter` (`eq` and `not`). |
| birthday | DateTimeOffset | The birthday of the user. The Timestamp type represents date and time information using ISO 8601 format and is always in UTC. For example, midnight UTC on Jan 1, 2014, is `2014-01-01T00:00:00Z`. <br>Requires `$select` to retrieve. |
| businessPhones | String collection | The telephone numbers for the user. NOTE: Although it's a string collection, only one number can be set for this property. Read-only for users synced from the on-premises directory. <br>Returned by default. Supports `$filter` (`eq`, `not`, `ge`, `le`, `startsWith`). |
| city | String | The city where the user is located. Maximum length is 128 characters. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| companyName | String | The name of the company that the user is associated with. This property can be useful for describing the company that a guest comes from. The maximum length is 64 characters.<br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| consentProvidedForMinor | [consentProvidedForMinor](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0#consentprovidedforminor-values) | Sets whether consent was obtained for minors. Allowed values: `null`, `Granted`, `Denied`, and `NotRequired`. For more information, see [legal age group property definitions](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0#legal-age-group-property-definitions). <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, and `in`). |
| country | String | The country or region where the user is located; for example, `US` or `UK`. Maximum length is 128 characters. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| createdDateTime | DateTimeOffset | The date and time the user was created, in ISO 8601 format and UTC. The value can't be modified and is automatically populated when the entity is created. Nullable. For on-premises users, the value represents when they were first created in Microsoft Entra ID. Property is `null` for some users created before June 2018 and on-premises users that were synced to Microsoft Entra ID before June 2018. Read-only. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`). |
| creationType | String | Indicates whether the user account was created through one of the following methods: <br>- As a regular school or work account (`null`). <br>- As an external account (`Invitation`). <br>- As a local account for an Azure Active Directory B2C tenant (`LocalAccount`). <br>- Through self-service sign-up by an internal user using email verification (`EmailVerified`). <br>- Through self-service sign-up by a guest signing up through a link that is part of a user flow (`SelfServiceSignUp`).<br>Read-only.<br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `in`). |
| customSecurityAttributes | [customSecurityAttributeValue](https://learn.microsoft.com/en-us/graph/api/resources/customsecurityattributevalue?view=graph-rest-1.0) | An open complex type that holds the value of a custom security attribute that is assigned to a directory object. Nullable. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `startsWith`). The filter value is case-sensitive. <br>To read this property, the calling app must be assigned the _CustomSecAttributeAssignment.Read.All_ permission. To write this property, the calling app must be assigned the _CustomSecAttributeAssignment.ReadWrite.All_ permissions. <br>To read or write this property in delegated scenarios, the admin must be assigned the _Attribute Assignment Administrator_ role. |
| deletedDateTime | DateTimeOffset | The date and time the user was deleted. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`). |
| department | String | The name of the department in which the user works. Maximum length is 64 characters. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`, and `eq` on `null` values). |
| displayName | String | The name displayed in the address book for the user. This value is usually the combination of the user's first name, middle initial, and family name. This property is required when a user is created and it can't be cleared during updates. Maximum length is 256 characters. <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values), `$orderby`, and `$search`. |
| employeeHireDate | DateTimeOffset | The date and time when the user was hired or will start work in a future hire. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`). |
| employeeLeaveDateTime | DateTimeOffset | The date and time when the user left or will leave the organization. <br>To read this property, the calling app must be assigned the _User-LifeCycleInfo.Read.All_ permission. To write this property, the calling app must be assigned the _User.Read.All_ and _User-LifeCycleInfo.ReadWrite.All_ permissions. <br>To read this property in delegated scenarios, the admin needs at least one of the following Microsoft Entra roles: _Lifecycle Workflows Administrator_ (least privilege), _Global Reader_. To write this property in delegated scenarios, the admin needs the _Global Administrator_ role. <br>Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`). <br>For more information, see [Configure the employeeLeaveDateTime property for a user](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-set-employeeleavedatetime). |
| employeeId | String | The employee identifier assigned to the user by the organization. The maximum length is 16 characters. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| employeeOrgData | [employeeOrgData](https://learn.microsoft.com/en-us/graph/api/resources/employeeorgdata?view=graph-rest-1.0) | Represents organization data (for example, division and costCenter) associated with a user. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`). |
| employeeType | String | Captures enterprise worker type. For example, `Employee`, `Contractor`, `Consultant`, or `Vendor`. Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`, `startsWith`). |
| externalUserState | String | For a guest invited to the tenant using the [invitation API](https://learn.microsoft.com/en-us/graph/api/invitation-post?view=graph-rest-1.0), this property represents the invited user's invitation status. For invited users, the state can be `PendingAcceptance` or `Accepted`, or `null` for all other users. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not` , `in`). |
| externalUserStateChangeDateTime | DateTimeOffset | Shows the timestamp for the latest change to the **externalUserState** property. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not` , `in`). |
| faxNumber | String | The fax number of the user. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| givenName | String | The given name (first name) of the user. Maximum length is 64 characters. <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| hireDate | DateTimeOffset | The hire date of the user. The Timestamp type represents date and time information using ISO 8601 format and is always in UTC. For example, midnight UTC on Jan 1, 2014, is `2014-01-01T00:00:00Z`. <br>Requires `$select` to retrieve. <br>**Note:** This property is specific to SharePoint in Microsoft 365. We recommend using the native **employeeHireDate** property to set and update hire date values using Microsoft Graph APIs. |
| id | String | The unique identifier for the user. Should be treated as an opaque identifier. Inherited from [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0). Key. Not nullable. Read-only. <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not`, `in`). |
| identities | [objectIdentity](https://learn.microsoft.com/en-us/graph/api/resources/objectidentity?view=graph-rest-1.0) collection | Represents the identities that can be used to sign in to this user account. Microsoft (also known as a local account), organizations, or social identity providers such as Facebook, Google, and Microsoft can provide identity and tie it to a user account. It might contain multiple items with the same **signInType** value. <br>Requires `$select` to retrieve. <br> Supports `$filter` (`eq`) with limitations. |
| imAddresses | String collection | The instant message voice-over IP (VOIP) session initiation protocol (SIP) addresses for the user. Read-only. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `not`, `ge`, `le`, `startsWith`). |
| interests | String collection | A list for the user to describe their interests. <br>Requires `$select` to retrieve. |
| isManagementRestricted | Boolean | `true` if the user is a member of a restricted management administrative unit. If not set, the default value is `null` and the default behavior is false. Read-only. <br> To manage a user who is a member of a restricted management administrative unit, the administrator or calling app must be assigned a Microsoft Entra role at the scope of the restricted management administrative unit. <br>Requires `$select` to retrieve. |
| isResourceAccount | Boolean | Don't use – reserved for future use. |
| jobTitle | String | The user's job title. Maximum length is 128 characters. <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not` , `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| lastPasswordChangeDateTime | DateTimeOffset | The time when this Microsoft Entra user last changed their password or when their password was created, whichever date the latest action was performed. The date and time information uses ISO 8601 format and is always in UTC. For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z`. <br>Requires `$select` to retrieve. |
| legalAgeGroupClassification | [legalAgeGroupClassification](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0#legalagegroupclassification-values) | Used by enterprise applications to determine the legal age group of the user. This property is read-only and calculated based on **ageGroup** and **consentProvidedForMinor** properties. Allowed values: `null`, `Undefined`, `MinorWithOutParentalConsent`, `MinorWithParentalConsent`, `MinorNoParentalConsentRequired`, `NotAdult`, and `Adult`. For more information, see [legal age group property definitions](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0#legal-age-group-property-definitions). <br>Requires `$select` to retrieve. |
| licenseAssignmentStates | [licenseAssignmentState](https://learn.microsoft.com/en-us/graph/api/resources/licenseassignmentstate?view=graph-rest-1.0) collection | State of license assignments for this user. Also indicates licenses that are directly assigned or the user inherited through group memberships. Read-only. <br>Requires `$select` to retrieve. |
| mail | String | The SMTP address for the user, for example, `jeff@contoso.com`. Changes to this property update the user's **proxyAddresses** collection to include the value as an SMTP address. This property can't contain accent characters. <br>**NOTE:** We don't recommend updating this property for Azure AD B2C user profiles. Use the **otherMails** property instead. <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, `endsWith`, and `eq` on `null` values). |
| mailboxSettings | [mailboxSettings](https://learn.microsoft.com/en-us/graph/api/resources/mailboxsettings?view=graph-rest-1.0) | Settings for the primary mailbox of the signed-in user. You can [get](https://learn.microsoft.com/en-us/graph/api/user-get-mailboxsettings?view=graph-rest-1.0) or [update](https://learn.microsoft.com/en-us/graph/api/user-update-mailboxsettings?view=graph-rest-1.0) settings for sending automatic replies to incoming messages, locale, and time zone. <br>Requires `$select` to retrieve. |
| mailNickname | String | The mail alias for the user. This property must be specified when a user is created. Maximum length is 64 characters. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| mobilePhone | String | The primary cellular telephone number for the user. Read-only for users synced from the on-premises directory. Maximum length is 64 characters. <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values) and `$search`. |
| mySite | String | The URL for the user's site. <br>Requires `$select` to retrieve. |
| officeLocation | String | The office location in the user's place of business. <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| onPremisesDistinguishedName | String | Contains the on-premises Active Directory `distinguished name` or `DN`. The property is only populated for customers who are synchronizing their on-premises directory to Microsoft Entra ID via Microsoft Entra Connect. Read-only. <br>Requires `$select` to retrieve. |
| onPremisesDomainName | String | Contains the on-premises `domainFQDN`, also called dnsDomainName synchronized from the on-premises directory. The property is only populated for customers who are synchronizing their on-premises directory to Microsoft Entra ID via Microsoft Entra Connect. Read-only. <br>Requires `$select` to retrieve. |
| onPremisesExtensionAttributes | [onPremisesExtensionAttributes](https://learn.microsoft.com/en-us/graph/api/resources/onpremisesextensionattributes?view=graph-rest-1.0) | Contains extensionAttributes1-15 for the user. These extension attributes are also known as Exchange custom attributes 1-15. Each attribute can store up to 1024 characters. <br>For an **onPremisesSyncEnabled** user, the source of authority for this set of properties is the on-premises and is read-only. <br>For a cloud-only user (where **onPremisesSyncEnabled** is `false`), these properties can be set during the creation or update of a user object. <br>For a cloud-only user previously synced from on-premises Active Directory, these properties are read-only in Microsoft Graph but can be fully managed through the Exchange Admin Center or the Exchange Online V2 module in PowerShell.<br> Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `in`). |
| onPremisesImmutableId | String | This property is used to associate an on-premises Active Directory user account to their Microsoft Entra user object. This property must be specified when creating a new user account in the Graph if you're using a federated domain for the user's **userPrincipalName** (UPN) property. **NOTE:** The **$** and **\_** characters can't be used when specifying this property. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`). |
| onPremisesLastSyncDateTime | DateTimeOffset | Indicates the last time at which the object was synced with the on-premises directory; for example: `2013-02-16T03:04:54Z`. The Timestamp type represents date and time information using ISO 8601 format and is always in UTC. For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z`. Read-only. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`). |
| onPremisesProvisioningErrors | [onPremisesProvisioningError](https://learn.microsoft.com/en-us/graph/api/resources/onpremisesprovisioningerror?view=graph-rest-1.0) collection | Errors when using Microsoft synchronization product during provisioning. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `not`, `ge`, `le`). |
| onPremisesSamAccountName | String | Contains the on-premises `samAccountName` synchronized from the on-premises directory. The property is only populated for customers who are synchronizing their on-premises directory to Microsoft Entra ID via Microsoft Entra Connect. Read-only. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`). |
| onPremisesSecurityIdentifier | String | Contains the on-premises security identifier (SID) for the user that was synchronized from on-premises to the cloud. Read-only. <br>Requires `$select` to retrieve. Supports `$filter` (`eq` including on `null` values). |
| onPremisesSyncEnabled | Boolean | `true` if this user object is currently being synced from an on-premises Active Directory (AD); otherwise the user isn't being synced and can be managed in Microsoft Entra ID. Read-only. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `in`, and `eq` on `null` values). |
| onPremisesUserPrincipalName | String | Contains the on-premises `userPrincipalName` synchronized from the on-premises directory. The property is only populated for customers who are synchronizing their on-premises directory to Microsoft Entra ID via Microsoft Entra Connect. Read-only. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`). |
| otherMails | String collection | A list of other email addresses for the user; for example: `["bob@contoso.com", "Robert@fabrikam.com"]`. Can store up to 250 values, each with a limit of 250 characters. <br>NOTE: This property can't contain accent characters. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `not`, `ge`, `le`, `in`, `startsWith`, `endsWith`, `/$count eq 0`, `/$count ne 0`). |
| passwordPolicies | String | Specifies password policies for the user. This value is an enumeration with one possible value being `DisableStrongPassword`, which allows weaker passwords than the default policy to be specified. `DisablePasswordExpiration` can also be specified. The two might be specified together; for example: `DisablePasswordExpiration, DisableStrongPassword`. <br>Requires `$select` to retrieve. For more information on the default password policies, see [Microsoft Entra password policies](https://learn.microsoft.com/en-us/azure/active-directory/authentication/concept-sspr-policy#password-policies-that-only-apply-to-cloud-user-accounts). Supports `$filter` (`ne`, `not`, and `eq` on `null` values). |
| passwordProfile | [passwordProfile](https://learn.microsoft.com/en-us/graph/api/resources/passwordprofile?view=graph-rest-1.0) | Specifies the password profile for the user. The profile contains the user's password. This property is required when a user is created. The password in the profile must satisfy minimum requirements as specified by the **passwordPolicies** property. By default, a strong password is required. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `in`, and `eq` on `null` values). <br>To update this property: <br>_User-PasswordProfile.ReadWrite.All_ is the least privileged permission to update this property. <br>In delegated scenarios, the _User Administrator_ [Microsoft Entra role](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/permissions-reference?toc=%2Fgraph%2Ftoc.json) is the least privileged admin role supported to update this property for nonadmin users. _Privileged Authentication Administrator_ is the least privileged role that's allowed to update this property for _all_ administrators in the tenant. In general, the signed-in user must have a higher privileged administrator role as indicated in [Who can reset passwords](https://learn.microsoft.com/en-us/graph/api/resources/users?view=graph-rest-1.0#who-can-reset-passwords). <br>In app-only scenarios, the calling app must be assigned a supported permission _and_ at least the _User Administrator_ [Microsoft Entra role](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/permissions-reference?toc=%2Fgraph%2Ftoc.json). |
| pastProjects | String collection | A list for the user to enumerate their past projects. <br>Requires `$select` to retrieve. |
| postalCode | String | The postal code for the user's postal address. The postal code is specific to the user's country or region. In the United States of America, this attribute contains the ZIP code. Maximum length is 40 characters. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| preferredDataLocation | String | The preferred data location for the user. For more information, see [OneDrive Online Multi-Geo](https://learn.microsoft.com/en-us/sharepoint/dev/solution-guidance/multigeo-introduction). |
| preferredLanguage | String | The preferred language for the user. The preferred language format is based on RFC 4646. The name is a combination of an ISO 639 two-letter lowercase culture code associated with the language, and an ISO 3166 two-letter uppercase subculture code associated with the country or region. Example: "en-US", or "es-ES". <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values) |
| preferredName | String | The preferred name for the user. **Not Supported. This attribute returns an empty string.**<br>Requires `$select` to retrieve. |
| provisionedPlans | [provisionedPlan](https://learn.microsoft.com/en-us/graph/api/resources/provisionedplan?view=graph-rest-1.0) collection | The plans that are provisioned for the user. Read-only. Not nullable. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `not`, `ge`, `le`). |
| proxyAddresses | String collection | For example: `["SMTP: bob@contoso.com", "smtp: bob@sales.contoso.com"]`. Changes to the **mail** property update this collection to include the value as an SMTP address. For more information, see [mail and proxyAddresses properties](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0#mail-and-proxyaddresses-properties). The proxy address prefixed with `SMTP` (capitalized) is the primary proxy address, while those addresses prefixed with `smtp` are the secondary proxy addresses. For Azure AD B2C accounts, this property has a limit of 10 unique addresses. Read-only in Microsoft Graph; you can update this property only through the [Microsoft 365 admin center](https://learn.microsoft.com/en-us/exchange/recipients-in-exchange-online/manage-user-mailboxes/add-or-remove-email-addresses). Not nullable. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `not`, `ge`, `le`, `startsWith`, `endsWith`, `/$count eq 0`, `/$count ne 0`). |
| refreshTokensValidFromDateTime | DateTimeOffset | Any refresh tokens or session tokens (session cookies) issued before this time are invalid. Applications get an error when using an invalid refresh or session token to acquire a delegated access token (to access APIs such as Microsoft Graph). If this happens, the application needs to acquire a new refresh token by requesting the authorized endpoint. <br>Requires `$select` to retrieve. Read-only. |
| responsibilities | String collection | A list for the user to enumerate their responsibilities. <br>Requires `$select` to retrieve. |
| serviceProvisioningErrors | [serviceProvisioningError](https://learn.microsoft.com/en-us/graph/api/resources/serviceprovisioningerror?view=graph-rest-1.0) collection | Errors published by a federated service describing a nontransient, service-specific error regarding the properties or link from a user object. <br> Supports `$filter` (`eq`, `not`, for isResolved and serviceInstance). |
| schools | String collection | A list for the user to enumerate the schools they attended. <br>Requires `$select` to retrieve. |
| securityIdentifier | String | Security identifier (SID) of the user, used in Windows scenarios. <br>Read-only. Returned by default. <br>Supports `$select` and `$filter` (`eq`, `not`, `ge`, `le`, `startsWith`). |
| showInAddressList | Boolean | **Do not use in Microsoft Graph. Manage this property through the Microsoft 365 admin center instead.** Represents whether the user should be included in the Outlook global address list. See [Known issue](https://learn.microsoft.com/en-us/graph/known-issues#showinaddresslist-property-is-out-of-sync-with-microsoft-exchange). |
| signInActivity | [signInActivity](https://learn.microsoft.com/en-us/graph/api/resources/signinactivity?view=graph-rest-1.0) | Get the last signed-in date and request ID of the sign-in for a given user. Read-only.<br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`) _but not with any other filterable properties_. <br>**Note:**<br>Details for this property require a Microsoft Entra ID P1 or P2 license and the **AuditLog.Read.All** permission.<br>This property isn't returned for a user who never signed in or last signed in before April 2020. |
| signInSessionsValidFromDateTime | DateTimeOffset | Any refresh tokens or session tokens (session cookies) issued before this time are invalid. Applications get an error when using an invalid refresh or session token to acquire a delegated access token (to access APIs such as Microsoft Graph). If this happens, the application needs to acquire a new refresh token by requesting the authorized endpoint. Read-only. Use [revokeSignInSessions](https://learn.microsoft.com/en-us/graph/api/user-revokesigninsessions?view=graph-rest-1.0) to reset. <br>Requires `$select` to retrieve. |
| skills | String collection | A list for the user to enumerate their skills. <br>Requires `$select` to retrieve. |
| state | String | The state or province in the user's address. Maximum length is 128 characters. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| streetAddress | String | The street address of the user's place of business. Maximum length is 1,024 characters. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| surname | String | The user's surname (family name or last name). Maximum length is 64 characters. <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| usageLocation | String | A two-letter country code (ISO standard 3166). Required for users that are assigned licenses due to legal requirements to check for availability of services in countries/regions. Examples include: `US`, `JP`, and `GB`. Not nullable. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, and `eq` on `null` values). |
| userPrincipalName | String | The user principal name (UPN) of the user. The UPN is an Internet-style sign-in name for the user based on the Internet standard RFC 822. By convention, this value should map to the user's email name. The general format is alias@domain, where the domain must be present in the tenant's collection of verified domains. This property is required when a user is created. The verified domains for the tenant can be accessed from the **verifiedDomains** property of [organization](https://learn.microsoft.com/en-us/graph/api/resources/organization?view=graph-rest-1.0).<br>NOTE: This property can't contain accent characters. Only the following characters are allowed `A - Z`, `a - z`, `0 - 9`, ` ' . - _ ! # ^ ~`. For the complete list of allowed characters, see [username policies](https://learn.microsoft.com/en-us/azure/active-directory/authentication/concept-sspr-policy#userprincipalname-policies-that-apply-to-all-user-accounts). <br>Returned by default. Supports `$filter` (`eq`, `ne`, `not`, `ge`, `le`, `in`, `startsWith`, `endsWith`) and `$orderby`. |
| userType | String | A string value that can be used to classify user types in your directory. The possible values are `Member` and `Guest`. <br>Requires `$select` to retrieve. Supports `$filter` (`eq`, `ne`, `not`, `in`, and `eq` on `null` values). **NOTE:** For more information about the permissions for members and guests, see [What are the default user permissions in Microsoft Entra ID?](https://learn.microsoft.com/en-us/azure/active-directory/fundamentals/users-default-permissions?context=graph/context#member-and-guest-users) |

Tip

Directory and schema extensions and their associated data require `$select` to retrieve; Open extensions and their associated data are returned only on `$expand`.

### mail and proxyAddresses properties

**mail** and **proxyAddresses** are both email-related properties. The **proxyAddresses** property is a collection of addresses only relevant to the Microsoft Exchange server. It's used to store a list of mail addresses for a user that are tied to a single mailbox. The **mail** property is used as the user's email address for various purposes including user sign-in and defines the primary proxy address.

Both **mail** and **proxyAddresses** can be retrieved through the [GET user](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0) API. You can update the **mail** via the [Update user](https://learn.microsoft.com/en-us/graph/api/user-update?view=graph-rest-1.0) API, but can't update **proxyAddresses** through Microsoft Graph. When a user's **mail** property is updated, it triggers recalculation of **proxyAddresses** and the newly updated mail is set to be the primary proxy address, except in the following scenarios:

1. If a user has a license that includes Microsoft Exchange, all their proxy addresses must belong to a verified domain on the tenant. Any that don't belong to verified domains are silently removed.
2. A user's mail is NOT set to the primary proxy address if the user is a guest and the primary proxy address contains the guest's UPN string with #EXT#.
3. A user's mail is NOT removed, even if they no longer have proxy addresses if the user is a guest.

**proxyAddresses** are unique across directory objects (users, groups, and organizational contacts). If a user's **mail** property conflicts with one of the **proxyAddresses** of another object, an attempt to update the **mail** fails, and the **proxyAddresses** property isn't updated either.

### Legal age group property definitions

This section explains how the three age group properties ( **legalAgeGroupClassification**, **ageGroup**, and **consentProvidedForMinor**) are used by Microsoft Entra administrators and enterprise application developers to meet age-related regulations:

- The **legalAgeGroupClassification** property is read-only. It's used by enterprise application developers to ensure the correct handling of a user based on their legal age group. It's calculated based on the user's **ageGroup** and **consentProvidedForMinor** properties.
- **ageGroup** and **consentProvidedForMinor** are optional properties used by Microsoft Entra administrators to help ensure the use of an account is handled correctly based on the age-related regulatory rules governing the user's country or region.

For example: Cameron is the administrator of a directory for an elementary school in Holyport in the United Kingdom. At the beginning of the school year, he uses the admissions paperwork to obtain consent from the minor's parents based on the age-related regulations of the United Kingdom. The consent obtained from the parent allows the minor's account to be used by Holyport School and Microsoft apps. Cameron then creates all the accounts and sets **ageGroup** to `minor` and **consentProvidedForMinor** to `granted`. Applications used by his students are then able to suppress features that aren't suitable for minors.

#### legalAgeGroupClassification values

| Member | Description |
| --- | --- |
| null | Default value, no **ageGroup** is set for the user. |
| Undefined | No **ageGroup** is set for the user but **consentProvidedForMinor** is either `Granted`, `Denied`, or `NotRequired`. |
| MinorWithoutParentalConsent | (Reserved for future use) |
| MinorWithParentalConsent | The user is considered a minor based on the age-related regulations of their country or region, and the administrator of the account obtained appropriate consent from a parent or guardian. |
| Adult | The user is considered an adult based on the age-related regulations of their country or region. |
| NotAdult | The user is from a country or region that has additional age-related regulations, such as the United States, United Kingdom, European Union, or South Korea, and the user's age is between a minor and an adult age (as stipulated based on country or region). Generally, this means that teenagers are considered as `notAdult` in regulated countries/regions. |
| MinorNoParentalConsentRequired | The user is a minor but is from a country or region that has no age-related regulations. |

#### ageGroup values

| Member | Description |
| --- | --- |
| null | Default value, no **ageGroup** is set for the user. |
| Minor | The user is considered a minor. |
| NotAdult | The user is from a country or region that has statutory regulations, such as the United States, United Kingdom, European Union, or South Korea, and the user's age is more than the upper limit of kid age (as per country or region) and less than lower limit of adult age (as stipulated based on country or region). So basically, teenagers are considered as `notAdult` in regulated countries/regions. |
| Adult | The user should be treated as an adult. |

#### consentProvidedForMinor values

| Member | Description |
| --- | --- |
| null | Default value, no **consentProvidedForMinor** is set for the user. |
| Granted | Consent is obtained for the user to have an account. |
| Denied | Consent isn't obtained for the user to have an account. |
| NotRequired | The user is from a location that doesn't require consent. |

## Relationships

| Relationship | Type | Description |
| --- | --- | --- |
| activities | [userActivity](https://learn.microsoft.com/en-us/graph/api/resources/projectrome-activity?view=graph-rest-1.0) collection | The user's activities across devices. Read-only. Nullable. |
| adhocCalls | [adhocCall](https://learn.microsoft.com/en-us/graph/api/resources/adhoccall?view=graph-rest-1.0) collection | Ad hoc calls associated with the user. Read-only. Nullable. |
| agreementAcceptances | [agreementAcceptance](https://learn.microsoft.com/en-us/graph/api/resources/agreementacceptance?view=graph-rest-1.0) collection | The user's terms of use acceptance statuses. Read-only. Nullable. |
| appRoleAssignments | [appRoleAssignment](https://learn.microsoft.com/en-us/graph/api/resources/approleassignment?view=graph-rest-1.0) collection | Represents the app roles a user is granted for an application. Supports `$expand`. |
| authentication | [authentication](https://learn.microsoft.com/en-us/graph/api/resources/authentication?view=graph-rest-1.0) | The authentication methods that are supported for the user. |
| calendar | [calendar](https://learn.microsoft.com/en-us/graph/api/resources/calendar?view=graph-rest-1.0) | The user's primary calendar. Read-only. |
| calendarGroups | [calendarGroup](https://learn.microsoft.com/en-us/graph/api/resources/calendargroup?view=graph-rest-1.0) collection | The user's calendar groups. Read-only. Nullable. |
| calendars | [calendar](https://learn.microsoft.com/en-us/graph/api/resources/calendar?view=graph-rest-1.0) collection | The user's calendars. Read-only. Nullable. |
| calendarView | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) collection | The calendar view for the calendar. Read-only. Nullable. |
| cloudPCs | [cloudPC](https://learn.microsoft.com/en-us/graph/api/resources/cloudpc?view=graph-rest-1.0) collection | The user's Cloud PCs. Read-only. Nullable. |
| contactFolders | [contactFolder](https://learn.microsoft.com/en-us/graph/api/resources/contactfolder?view=graph-rest-1.0) collection | The user's contacts folders. Read-only. Nullable. |
| contacts | [contact](https://learn.microsoft.com/en-us/graph/api/resources/contact?view=graph-rest-1.0) collection | The user's contacts. Read-only. Nullable. |
| createdObjects | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Directory objects that the user created. Read-only. Nullable. |
| dataSecurityAndGovernance | [userDataSecurityAndGovernance](https://learn.microsoft.com/en-us/graph/api/resources/userdatasecurityandgovernance?view=graph-rest-1.0) | The data security and governance settings for the user. Read-only. Nullable. |
| directReports | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | The users and contacts that report to the user. (The users and contacts that have their manager property set to this user.) Read-only. Nullable. Supports `$expand`. |
| drive | [drive](https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0) | The user's OneDrive. Read-only. |
| drives | [drive](https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0) collection | A collection of drives available for this user. Read-only. |
| events | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) collection | The user's events. Default is to show Events under the Default Calendar. Read-only. Nullable. |
| extensions | [extension](https://learn.microsoft.com/en-us/graph/api/resources/extension?view=graph-rest-1.0) collection | The collection of open extensions defined for the user. Read-only. Supports `$expand`. Nullable. |
| inferenceClassification | [inferenceClassification](https://learn.microsoft.com/en-us/graph/api/resources/inferenceclassification?view=graph-rest-1.0) | Relevance classification of the user's messages based on explicit designations that override inferred relevance or importance. |
| insights | [itemInsights](https://learn.microsoft.com/en-us/graph/api/resources/iteminsights?view=graph-rest-1.0) | Represents relationships between a user and items such as OneDrive for work or school documents, calculated using advanced analytics and machine learning techniques. Read-only. Nullable. |
| licenseDetails | [licenseDetails](https://learn.microsoft.com/en-us/graph/api/resources/licensedetails?view=graph-rest-1.0) collection | A collection of this user's license details. Read-only. |
| mailFolders | [mailFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0) collection | The user's mail folders. Read-only. Nullable. |
| manager | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) | The user or contact that is this user's manager. Read-only. Supports `$expand`. |
| memberOf | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | The groups and directory roles that the user is a member of. Read-only. Nullable. Supports `$expand`. |
| messages | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) collection | The messages in a mailbox or folder. Read-only. Nullable. |
| onenote | [onenote](https://learn.microsoft.com/en-us/graph/api/resources/onenote?view=graph-rest-1.0) | Read-only. |
| onlineMeetings | [onlineMeeting](https://learn.microsoft.com/en-us/graph/api/resources/onlinemeeting?view=graph-rest-1.0) collection | Information about a meeting, including the URL used to join a meeting, the attendees list, and the description. |
| outlook | [outlookUser](https://learn.microsoft.com/en-us/graph/api/resources/outlookuser?view=graph-rest-1.0) | Read-only. |
| ownedDevices | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Devices the user owns. Read-only. Nullable. Supports `$expand` and `$filter` (`/$count eq 0`, `/$count ne 0`, `/$count eq 1`, `/$count ne 1`). |
| ownedObjects | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Directory objects the user owns. Read-only. Nullable. Supports `$expand`, `$select` nested in `$expand`, and `$filter` (`/$count eq 0`, `/$count ne 0`, `/$count eq 1`, `/$count ne 1`). |
| people | [person](https://learn.microsoft.com/en-us/graph/api/resources/person?view=graph-rest-1.0) collection | People that are relevant to the user. Read-only. Nullable. |
| permissionGrants | [resourceSpecificPermissionGrant](https://learn.microsoft.com/en-us/graph/api/resources/resourcespecificpermissiongrant?view=graph-rest-1.0) collection | List all resource-specific permission grants of a user. |
| photo | [profilePhoto](https://learn.microsoft.com/en-us/graph/api/resources/profilephoto?view=graph-rest-1.0) | The user's profile photo. Read-only. |
| photos | [profilePhoto](https://learn.microsoft.com/en-us/graph/api/resources/profilephoto?view=graph-rest-1.0) collection | The collection of the user's profile photos in different sizes. Read-only. |
| planner | [plannerUser](https://learn.microsoft.com/en-us/graph/api/resources/planneruser?view=graph-rest-1.0) | Entry-point to the Planner resource that might exist for a user. Read-only. |
| registeredDevices | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | Devices that are registered for the user. Read-only. Nullable. Supports `$expand` and returns up to 100 objects. |
| solutions | [userSolutionRoot](https://learn.microsoft.com/en-us/graph/api/resources/usersolutionroot?view=graph-rest-1.0) | The identifier that relates the user to the working time schedule triggers. Read-Only. Nullable |
| sponsors | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | The users and groups responsible for this guest's privileges in the tenant and keeping the guest's information and access updated. (HTTP Methods: GET, POST, DELETE.). Supports `$expand`. |
| teamwork | [userTeamwork](https://learn.microsoft.com/en-us/graph/api/resources/userteamwork?view=graph-rest-1.0) | A container for Microsoft Teams features available for the user. Read-only. Nullable. |
| todo | [todo](https://learn.microsoft.com/en-us/graph/api/resources/todo?view=graph-rest-1.0) | Represents the To Do services available to a user. |
| transitiveMemberOf | [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0) collection | The groups, including nested groups, and directory roles that a user is a member of. Nullable. |

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "aboutMe": "String",
  "accountEnabled": true,
  "ageGroup": "String",
  "assignedLicenses": [{"@odata.type": "microsoft.graph.assignedLicense"}],
  "assignedPlans": [{"@odata.type": "microsoft.graph.assignedPlan"}],
  "birthday": "String (timestamp)",
  "businessPhones": ["String"],
  "city": "String",
  "companyName": "String",
  "consentProvidedForMinor": "String",
  "country": "String",
  "createdDateTime": "String (timestamp)",
  "creationType": "String",
  "customSecurityAttributes": {
    "@odata.type": "microsoft.graph.customSecurityAttributeValue"
  },
  "department": "String",
  "displayName": "String",
  "employeeHireDate": "2020-01-01T00:00:00Z",
  "employeeId": "String",
  "employeeOrgData": {"@odata.type": "microsoft.graph.employeeOrgData"},
  "employeeType": "String",
  "faxNumber" : "String",
  "givenName": "String",
  "hireDate": "String (timestamp)",
  "id": "String (identifier)",
  "identities": [{"@odata.type": "microsoft.graph.objectIdentity"}],
  "imAddresses": ["String"],
  "interests": ["String"],
  "isManagementRestricted": "Boolean",
  "isResourceAccount": false,
  "jobTitle": "String",
  "legalAgeGroupClassification": "String",
  "licenseAssignmentStates": [{"@odata.type": "microsoft.graph.licenseAssignmentState"}],
  "lastPasswordChangeDateTime": "String (timestamp)",
  "mail": "String",
  "mailboxSettings": {"@odata.type": "microsoft.graph.mailboxSettings"},
  "mailNickname": "String",
  "mobilePhone": "String",
  "mySite": "String",
  "officeLocation": "String",
  "onPremisesDistinguishedName": "String",
  "onPremisesDomainName": "String",
  "onPremisesExtensionAttributes": {"@odata.type": "microsoft.graph.onPremisesExtensionAttributes"},
  "onPremisesImmutableId": "String",
  "onPremisesLastSyncDateTime": "String (timestamp)",
  "onPremisesProvisioningErrors": [{"@odata.type": "microsoft.graph.onPremisesProvisioningError"}],
  "onPremisesSamAccountName": "String",
  "onPremisesSecurityIdentifier": "String",
  "onPremisesSyncEnabled": true,
  "onPremisesUserPrincipalName": "String",
  "otherMails": ["String"],
  "passwordPolicies": "String",
  "passwordProfile": {"@odata.type": "microsoft.graph.passwordProfile"},
  "pastProjects": ["String"],
  "postalCode": "String",
  "preferredDataLocation": "String",
  "preferredLanguage": "String",
  "preferredName": "String",
  "provisionedPlans": [{"@odata.type": "microsoft.graph.provisionedPlan"}],
  "proxyAddresses": ["String"],
  "responsibilities": ["String"],
  "schools": ["String"],
  "securityIdentifier": "String",
  "serviceProvisioningErrors": [\
    { "@odata.type": "microsoft.graph.serviceProvisioningXmlError" }\
  ],
  "showInAddressList": true,
  "signInActivity": {"@odata.type": "microsoft.graph.signInActivity"},
  "signInSessionsValidFromDateTime": "String (timestamp)",
  "skills": ["String"],
  "state": "String",
  "streetAddress": "String",
  "surname": "String",
  "usageLocation": "String",
  "userPrincipalName": "String",
  "userType": "String",

  "calendar": { "@odata.type": "microsoft.graph.calendar" },
  "calendarGroups": [{ "@odata.type": "microsoft.graph.calendarGroup" }],
  "calendarView": [{ "@odata.type": "microsoft.graph.event" }],
  "calendars": [ {"@odata.type": "microsoft.graph.calendar"} ],
  "contacts": [ { "@odata.type": "microsoft.graph.contact" } ],
  "contactFolders": [ { "@odata.type": "microsoft.graph.contactFolder" } ],
  "createdObjects": [ { "@odata.type": "microsoft.graph.directoryObject" } ],
  "directReports": [ { "@odata.type": "microsoft.graph.directoryObject" } ],
  "drive": { "@odata.type": "microsoft.graph.drive" },
  "drives": [ { "@odata.type": "microsoft.graph.drive" } ],
  "events": [ { "@odata.type": "microsoft.graph.event" } ],
  "inferenceClassification": { "@odata.type": "microsoft.graph.inferenceClassification" },
  "mailFolders": [ { "@odata.type": "microsoft.graph.mailFolder" } ],
  "manager": { "@odata.type": "microsoft.graph.directoryObject" },
  "memberOf": [ { "@odata.type": "microsoft.graph.directoryObject" } ],
  "messages": [ { "@odata.type": "microsoft.graph.message" } ],
  "outlook": { "@odata.type": "microsoft.graph.outlookUser" },
  "ownedDevices": [ { "@odata.type": "microsoft.graph.directoryObject" } ],
  "ownedObjects": [ { "@odata.type": "microsoft.graph.directoryObject" } ],
  "photo": { "@odata.type": "microsoft.graph.profilePhoto" },
  "photos": [ { "@odata.type": "microsoft.graph.profilePhoto" } ],
  "registeredDevices": [ { "@odata.type": "microsoft.graph.directoryObject" } ]
}
```

## Related content

- [Add custom data to resources using extensions](https://learn.microsoft.com/en-us/graph/extensibility-overview)
- [Add custom data to users using open extensions](https://learn.microsoft.com/en-us/graph/extensibility-open-users)
- [Add custom data to groups using schema extensions](https://learn.microsoft.com/en-us/graph/extensibility-schema-groups)

* * *
