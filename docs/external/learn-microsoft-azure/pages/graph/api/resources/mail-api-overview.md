# Use the Outlook mail REST API

Microsoft Graph lets your app get authorized access to a user's Outlook mail data in a personal or organization account.
With the appropriate delegated or application [mail permissions](https://learn.microsoft.com/en-us/graph/permissions-reference#mail-permissions), your app can access the mail data of the signed-in user or any user in a tenant. For more information on access tokens, app registration, and delegated and application permissions, see [Authentication and authorization basics](https://learn.microsoft.com/en-us/graph/auth/auth-concepts).

The Microsoft Graph API supports accessing data in users' _primary_ mailboxes and in [shared mailboxes](https://support.office.com/article/open-and-use-a-shared-mailbox-in-outlook-d94a8e9e-21f1-4240-808b-de9c9c088afd). The data can be calendar, mail, or personal contacts stored in a mailbox in the cloud on Exchange Online as part of Microsoft 365, or on Exchange on-premises in a [hybrid deployment](https://learn.microsoft.com/en-us/graph/hybrid-rest-support).

The API does _not_ support accessing in-place archive mailboxes, not [on Exchange Online](https://learn.microsoft.com/en-us/microsoft-365/compliance/enable-archive-mailboxes) nor [on Exchange Server](https://learn.microsoft.com/en-us/Exchange/policy-and-compliance/in-place-archiving/in-place-archiving?view=exchserver-2019&preserve-view=true).

## Using the mail REST API

Mail API requests are performed on behalf of a [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) which can be identified by the user's **id** property (a unique GUID), email address,
or the `me` shortcut alias for the signed-in user.

Email messages are represented by the [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) resource and organized in a [mailFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0).
Messages and mail folders are identified by their **id** property, obtainable from `GET` operations.

Important

In general, do not assume that **message** and **mailfolder** IDs are unique and always remain the same within a mailbox. They might change after certain
actions such as copy or move. You can choose to use [immutable IDs](https://learn.microsoft.com/en-us/graph/outlook-immutable-id) to retain the same ID as long as the message remains in the same mailbox, _with the exception of sending a draft message, and a few other scenarios_. See [lifetime of immutable IDs](https://learn.microsoft.com/en-us/graph/outlook-immutable-id#lifetime-of-immutable-ids) for details.

Message bodies can be in HTML or text format.

You can use well-known folder names such as `Inbox`, `Drafts`, `SentItems`, or `DeletedItems` to identify certain mail folders that exist by default for all users. For a list of supported well-known folder names, see [mailFolder resource type](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0).

For example, you can get messages in the Outlook **Sent Items** folder of the signed-in user, without first getting the folder ID:

HTTP

Copy

```http
GET /me/mailFolders('SentItems')/messages?$select=sender,subject
```

When a message is updated while open in an Outlook client, the client does not refresh the message. Users must reopen the message to view the changes.

## Common use cases

The **message** resource exposes properties such as **categories**, **conversationId**, **flag**, and **importance** that correspond to features
available in the UI, allowing apps to automate or integrate with the built-in Outlook user experience.

The Microsoft Graph API also provides methods and actions that support common use cases of messages.

| Use cases | REST resources | See also |
| --- | --- | --- |
| **User-centric actions** |  |  |
| Draft, read, reply, forward, send, update, or delete messages | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | [Methods of message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0#methods) |
| Delegate another user to send messages on behalf of the mailbox owner | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Setting the **from** and **sender** properties in a [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) |
| Let user view more important messages first | [inferenceClassificationOverride](https://learn.microsoft.com/en-us/graph/api/resources/inferenceclassificationoverride?view=graph-rest-1.0) | [Focused Inbox](https://learn.microsoft.com/en-us/graph/api/resources/manage-focused-inbox?view=graph-rest-1.0) |
| Query for messages and get them in a search folder | [mailSearchFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailsearchfolder?view=graph-rest-1.0) | [Methods of mailSearchFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailsearchfolder?view=graph-rest-1.0#methods) |
| Get the MIME content of a message or message attachment | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | [Get MIME content](https://learn.microsoft.com/en-us/graph/outlook-get-mime-message) |
| Send messages with MIME content | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | [Send MIME content](https://learn.microsoft.com/en-us/graph/outlook-send-mime-message) |
| Add, get, or delete attachments of a message | [attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0), <br>[fileAttachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment?view=graph-rest-1.0), <br>[itemAttachment](https://learn.microsoft.com/en-us/graph/api/resources/itemattachment?view=graph-rest-1.0), <br>[referenceAttachment](https://learn.microsoft.com/en-us/graph/api/resources/referenceattachment?view=graph-rest-1.0), <br>[message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | [Methods of attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0#methods) |
| Get language and time zone choices for a user | [localeInfo](https://learn.microsoft.com/en-us/graph/api/resources/localeinfo?view=graph-rest-1.0), <br>[timeZoneInformation](https://learn.microsoft.com/en-us/graph/api/resources/timezoneinformation?view=graph-rest-1.0) | [supportedLanguages](https://learn.microsoft.com/en-us/graph/api/outlookuser-supportedlanguages?view=graph-rest-1.0), <br>[supportedTimeZones](https://learn.microsoft.com/en-us/graph/api/outlookuser-supportedtimezones?view=graph-rest-1.0) |
| Get or update a user's automatic reply, locale, time zone, or working hours | [mailboxSettings](https://learn.microsoft.com/en-us/graph/api/resources/mailboxsettings?view=graph-rest-1.0), <br>[automaticRepliesSetting](https://learn.microsoft.com/en-us/graph/api/resources/automaticrepliessetting?view=graph-rest-1.0), <br>[localeInfo](https://learn.microsoft.com/en-us/graph/api/resources/localeinfo?view=graph-rest-1.0), <br>[workingHours](https://learn.microsoft.com/en-us/graph/api/resources/workinghours?view=graph-rest-1.0) | [Get user's mailbox settings](https://learn.microsoft.com/en-us/graph/api/user-get-mailboxsettings?view=graph-rest-1.0), <br>[Update user's mailbox settings](https://learn.microsoft.com/en-us/graph/api/user-update-mailboxsettings?view=graph-rest-1.0) |
| Get MailTips of other recipients' special status, such as out-of-office | [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0), <br>[mailTips](https://learn.microsoft.com/en-us/graph/api/resources/mailtips?view=graph-rest-1.0) | [Get MailTips](https://learn.microsoft.com/en-us/graph/api/user-getmailtips?view=graph-rest-1.0) |
| **Mail and folder management** |  |  |
| Organize messages in a mail folder hierarchy | [mailFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0) | [Methods of mailFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0#methods) |
| Categorize messages | [outlookCategory](https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory?view=graph-rest-1.0) | [Methods of outlookCategory](https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory?view=graph-rest-1.0#methods) |
| Use Inbox rules to automate actions such as forwarding specific incoming messages | [messageRule](https://learn.microsoft.com/en-us/graph/api/resources/messagerule?view=graph-rest-1.0) | [Methods of messageRule](https://learn.microsoft.com/en-us/graph/api/resources/messagerule?view=graph-rest-1.0#methods) |
| Get Internet message headers of a message | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | [Get the **internetMessageHeaders** property of a message](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0#example-2-get-internet-message-headers). |
| Search and filter messages | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | [Query parameters](https://learn.microsoft.com/en-us/graph/query-parameters) |
| Get notified of changes to messages in a folder | [subscription](https://learn.microsoft.com/en-us/graph/api/resources/subscription?view=graph-rest-1.0) | [Working with webhooks in Microsoft Graph](https://learn.microsoft.com/en-us/graph/api/resources/change-notifications-api-overview?view=graph-rest-1.0) |
| Synchronize messages or mail folder hierarchy | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | [Get incremental changes to messages in a folder](https://learn.microsoft.com/en-us/graph/delta-query-messages) |
| Trace messages through the Exchange Online organization | [messageTrace](https://learn.microsoft.com/en-us/graph/api/resources/exchangemessagetrace?view=graph-rest-1.0) | [Methods of messageTrace](https://learn.microsoft.com/en-us/graph/api/resources/exchangemessagetrace?view=graph-rest-1.0#methods) |
| **App development** |  |  |
| Add custom app data as Internet message headers of a message | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Add custom data to the **internetMessageHeaders** property of the message. |
| Add custom app data to a message by using extensions | [openTypeExtension](https://learn.microsoft.com/en-us/graph/api/resources/opentypeextension?view=graph-rest-1.0), <br>[schemaExtension](https://learn.microsoft.com/en-us/graph/api/resources/schemaextension?view=graph-rest-1.0) | [Add custom data to resources using extensions](https://learn.microsoft.com/en-us/graph/extensibility-overview) |
| Access custom data for under-exposed Outlook MAPI properties | [singleValueLegacyExtendedProperty](https://learn.microsoft.com/en-us/graph/api/resources/singlevaluelegacyextendedproperty?view=graph-rest-1.0), <br>[multiValueLegacyExtendedProperty](https://learn.microsoft.com/en-us/graph/api/resources/multivaluelegacyextendedproperty?view=graph-rest-1.0) | [Outlook extended properties overview](https://learn.microsoft.com/en-us/graph/api/resources/extended-properties-overview?view=graph-rest-1.0) |

## Next steps

The mail API can open up new ways for you to engage with users:

- [Outlook mail API overview](https://learn.microsoft.com/en-us/graph/outlook-mail-concept-overview)
- Drill down on the [methods](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0#methods), [properties](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0#properties), and [relationships](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0#relationships) of the [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) and [mailFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder?view=graph-rest-1.0) resources.
- Try the API in the [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer).

* * *
