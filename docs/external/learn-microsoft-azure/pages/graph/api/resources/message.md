# message resource type

Namespace: microsoft.graph

A message in a mailFolder.

The maximum total number of recipients included in the **toRecipients**, **ccRecipients**, and **bccRecipients** properties for a single email message sent from an Exchange Online mailbox is 500. For more information, see [sending limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits#sending-limits).

This resource supports:

- Adding your own data as custom Internet message headers. Add custom headers only when creating a message, and name them starting with "x-". After the message is sent, you cannot modify the headers. To get the headers of a message, apply the `$select` query parameter in a [get message](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0) operation.
- Adding your own data as custom properties as [extensions](https://learn.microsoft.com/en-us/graph/extensibility-overview).
- Subscribing to [change notifications](https://learn.microsoft.com/en-us/graph/change-notifications-overview).
- Using [delta query](https://learn.microsoft.com/en-us/graph/delta-query-overview) to track incremental additions, deletions, and updates,
by providing a [delta](https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0) function.

## Methods

| Method | Return type | Description |
| --- | --- | --- |
| [List messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) collection | Get all the messages in the signed-in user's mailbox (including the Deleted Items and Clutter folders). |
| [Create draft message](https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | [Create](https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0#request-1) a draft of a new message. |
| [Get message](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Read properties and relationships of message object. |
| [Update message](https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Update message object. |
| [Delete message](https://learn.microsoft.com/en-us/graph/api/message-delete?view=graph-rest-1.0) | None | Delete message object. |
| [Copy message](https://learn.microsoft.com/en-us/graph/api/message-copy?view=graph-rest-1.0) | [Message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Copy a message to a folder. |
| [Create draft to forward message](https://learn.microsoft.com/en-us/graph/api/message-createforward?view=graph-rest-1.0) | [Message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Create a draft of the Forward message. You can then [update](https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0) or [send](https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0) the draft. |
| [Create draft to reply](https://learn.microsoft.com/en-us/graph/api/message-createreply?view=graph-rest-1.0) | [Message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Create a draft of the Reply message. You can then [update](https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0) or [send](https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0) the draft. |
| [Create draft to reply-all](https://learn.microsoft.com/en-us/graph/api/message-createreplyall?view=graph-rest-1.0) | [Message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Create a draft of the Reply All message. You can then [update](https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0) or [send](https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0) the draft. |
| [Get message delta](https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) collection | Get a set of messages that were added, deleted, or updated in a specified folder. |
| [Forward message](https://learn.microsoft.com/en-us/graph/api/message-forward?view=graph-rest-1.0) | None | Forward a message. The message is then saved in the Sent Items folder. |
| [Move message](https://learn.microsoft.com/en-us/graph/api/message-move?view=graph-rest-1.0) | [Message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Move the message to a folder. This creates a new copy of the message in the destination folder. |
| [Reply to a message](https://learn.microsoft.com/en-us/graph/api/message-reply?view=graph-rest-1.0) | None | Reply to the sender of a message. The message is then saved in the Sent Items folder. |
| [Reply-all to a message](https://learn.microsoft.com/en-us/graph/api/message-replyall?view=graph-rest-1.0) | None | Reply to all recipients of a message. The message is then saved in the Sent Items folder. |
| [Send draft message](https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0) | None | Sends a previously created message draft. The message is then saved in the Sent Items folder. |
| [Permanently delete](https://learn.microsoft.com/en-us/graph/api/message-permanentdelete?view=graph-rest-1.0) | None | Permanently delete a message and place it in the purges folder in the recoverable Items folder in the user's mailbox. |
| **Attachments** |  |  |
| [List attachments](https://learn.microsoft.com/en-us/graph/api/message-list-attachments?view=graph-rest-1.0) | [Attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0) collection | Gets all attachments on a message. |
| [Add attachment](https://learn.microsoft.com/en-us/graph/api/message-post-attachments?view=graph-rest-1.0) | [Attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0) | Add a new attachment to a message by posting to the attachments collection. |
| **Open extensions** |  |  |
| [Create open extension](https://learn.microsoft.com/en-us/graph/api/opentypeextension-post-opentypeextension?view=graph-rest-1.0) | [openTypeExtension](https://learn.microsoft.com/en-us/graph/api/resources/opentypeextension?view=graph-rest-1.0) | Create an open extension and add custom properties in a new or existing instance of a resource. |
| [Get open extension](https://learn.microsoft.com/en-us/graph/api/opentypeextension-get?view=graph-rest-1.0) | [openTypeExtension](https://learn.microsoft.com/en-us/graph/api/resources/opentypeextension?view=graph-rest-1.0) collection | Get an open extension object or objects identified by name or fully qualified name. |
| **Extended properties** |  |  |
| [Create single-value property](https://learn.microsoft.com/en-us/graph/api/singlevaluelegacyextendedproperty-post-singlevalueextendedproperties?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Create one or more single-value extended properties in a new or existing message. |
| [Get single-value property](https://learn.microsoft.com/en-us/graph/api/singlevaluelegacyextendedproperty-get?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Get messages that contain a single-value extended property by using `$expand` or `$filter`. |
| [Create multi-value property](https://learn.microsoft.com/en-us/graph/api/multivaluelegacyextendedproperty-post-multivalueextendedproperties?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Create one or more multi-value extended properties in a new or existing message. |
| [Get multi-value property](https://learn.microsoft.com/en-us/graph/api/multivaluelegacyextendedproperty-get?view=graph-rest-1.0) | [message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) | Get a message that contains a multi-value extended property by using `$expand`. |

## Properties

| Property | Type | Description |
| --- | --- | --- |
| bccRecipients | [recipient](https://learn.microsoft.com/en-us/graph/api/resources/recipient?view=graph-rest-1.0) collection | The Bcc: recipients for the message. |
| body | [itemBody](https://learn.microsoft.com/en-us/graph/api/resources/itembody?view=graph-rest-1.0) | The body of the message. It can be in HTML or text format. Find out about [safe HTML in a message body](https://learn.microsoft.com/en-us/graph/outlook-create-send-messages#reading-messages-with-control-over-the-body-format-returned). |
| bodyPreview | String | The first 255 characters of the message body. It is in text format. |
| ccRecipients | [recipient](https://learn.microsoft.com/en-us/graph/api/resources/recipient?view=graph-rest-1.0) collection | The Cc: recipients for the message. |
| changeKey | String | The version of the message. |
| conversationId | String | The ID of the conversation the email belongs to. |
| conversationIndex | Edm.Binary | Indicates the position of the message within the conversation. |
| createdDateTime | DateTimeOffset | The date and time the message was created. <br> The date and time information uses ISO 8601 format and is always in UTC time. For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z`. |
| flag | [followupFlag](https://learn.microsoft.com/en-us/graph/api/resources/followupflag?view=graph-rest-1.0) | Indicates the status, start date, due date, or completion date for the message. |
| from | [recipient](https://learn.microsoft.com/en-us/graph/api/resources/recipient?view=graph-rest-1.0) | The owner of the mailbox from which the message is sent. In most cases, this value is the same as the **sender** property, except for sharing or delegation scenarios. The value must correspond to the actual mailbox used. Find out more about [setting the from and sender properties](https://learn.microsoft.com/en-us/graph/outlook-create-send-messages#setting-the-from-and-sender-properties) of a message. |
| hasAttachments | Boolean | Indicates whether the message has attachments. This property doesn't include inline attachments, so if a message contains only inline attachments, this property is false. To verify the existence of inline attachments, parse the **body** property to look for a `src` attribute, such as `<IMG src="cid:image001.jpg@01D26CD8.6C05F070">`. |
| id | String | Unique identifier for the message. By default, this value changes when the item is moved from one container (such as a folder or calendar) to another. To change this behavior, use the `Prefer: IdType="ImmutableId"` header. See [Get immutable identifiers for Outlook resources](https://learn.microsoft.com/en-us/graph/outlook-immutable-id) for more information. Read-only. |
| importance | importance | The importance of the message. The possible values are: `low`, `normal`, and `high`. |
| inferenceClassification | inferenceClassificationType | The classification of the message for the user, based on inferred relevance or importance, or on an explicit override. The possible values are: `focused` or `other`. |
| internetMessageHeaders | [internetMessageHeader](https://learn.microsoft.com/en-us/graph/api/resources/internetmessageheader?view=graph-rest-1.0) collection | A collection of message headers defined by [RFC5322](https://www.ietf.org/rfc/rfc5322.txt). The set includes message headers indicating the network path taken by a message from the sender to the recipient. It can also contain custom message headers that hold app data for the message. <br> Requires `$select` to retrieve. Read-only. |
| internetMessageId | String | The message ID in the format specified by [RFC2822](https://www.ietf.org/rfc/rfc2822.txt). |
| isDeliveryReceiptRequested | Boolean | Indicates whether a read receipt is requested for the message. |
| isDraft | Boolean | Indicates whether the message is a draft. A message is a draft if it hasn't been sent yet. |
| isRead | Boolean | Indicates whether the message has been read. |
| isReadReceiptRequested | Boolean | Indicates whether a read receipt is requested for the message. |
| lastModifiedDateTime | DateTimeOffset | The date and time the message was last changed. <br> The date and time information uses ISO 8601 format and is always in UTC time. For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z`. |
| parentFolderId | String | The unique identifier for the message's parent mailFolder. |
| receivedDateTime | DateTimeOffset | The date and time the message was received. <br> The date and time information uses ISO 8601 format and is always in UTC time. For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z`. |
| replyTo | [recipient](https://learn.microsoft.com/en-us/graph/api/resources/recipient?view=graph-rest-1.0) collection | The email addresses to use when replying. |
| sender | [recipient](https://learn.microsoft.com/en-us/graph/api/resources/recipient?view=graph-rest-1.0) | The account that is used to generate the message. In most cases, this value is the same as the **from** property. You can set this property to a different value when sending a message from a [shared mailbox](https://learn.microsoft.com/en-us/exchange/collaboration/shared-mailboxes/shared-mailboxes), [for a shared calendar, or as a delegate](https://learn.microsoft.com/en-us/graph/outlook-share-or-delegate-calendar). In any case, the value must correspond to the actual mailbox used. Find out more about [setting the from and sender properties](https://learn.microsoft.com/en-us/graph/outlook-create-send-messages#setting-the-from-and-sender-properties) of a message. |
| sentDateTime | DateTimeOffset | The date and time the message was sent. <br> The date and time information uses ISO 8601 format and is always in UTC time. For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z`. |
| subject | String | The subject of the message. |
| toRecipients | [recipient](https://learn.microsoft.com/en-us/graph/api/resources/recipient?view=graph-rest-1.0) collection | The To: recipients for the message. |
| uniqueBody | [itemBody](https://learn.microsoft.com/en-us/graph/api/resources/itembody?view=graph-rest-1.0) | The part of the body of the message that is unique to the current message. **uniqueBody** is not returned by default but can be retrieved for a given message by use of the `?$select=uniqueBody` query. It can be in HTML or text format. |
| webLink | String | The URL to open the message in Outlook on the web.<br>You can append an `ispopout` argument to the end of the URL to change how the message is displayed. If `ispopout` is not present or if it is set to `1`, then the message is shown in a popout window. If `ispopout` is set to `0`, the browser shows the message in the Outlook on the web review pane.<br>The message opens in the browser if you are signed in to your mailbox via Outlook on the web. You are prompted to sign in if you are not already signed in with the browser.<br>This URL cannot be accessed from within an iFrame.<br>**NOTE:** When using this URL to access a message from a mailbox with delegate permissions, both the signed-in user and the target mailbox must be in the same database region. For example, an error is returned when a user with a mailbox in the EUR (Europe) region attempts to access messages from a mailbox in the NAM (North America) region. |

## Relationships

| Relationship | Type | Description |
| --- | --- | --- |
| attachments | [attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0) collection | The [fileAttachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment?view=graph-rest-1.0) and [itemAttachment](https://learn.microsoft.com/en-us/graph/api/resources/itemattachment?view=graph-rest-1.0) attachments for the message. |
| extensions | [extension](https://learn.microsoft.com/en-us/graph/api/resources/extension?view=graph-rest-1.0) collection | The collection of open extensions defined for the message. Nullable. |
| multiValueExtendedProperties | [multiValueLegacyExtendedProperty](https://learn.microsoft.com/en-us/graph/api/resources/multivaluelegacyextendedproperty?view=graph-rest-1.0) collection | The collection of multi-value extended properties defined for the message. Nullable. |
| singleValueExtendedProperties | [singleValueLegacyExtendedProperty](https://learn.microsoft.com/en-us/graph/api/resources/singlevaluelegacyextendedproperty?view=graph-rest-1.0) collection | The collection of single-value extended properties defined for the message. Nullable. |

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "bccRecipients": [{"@odata.type": "microsoft.graph.recipient"}],
  "body": {"@odata.type": "microsoft.graph.itemBody"},
  "bodyPreview": "string",
  "categories": ["string"],
  "ccRecipients": [{"@odata.type": "microsoft.graph.recipient"}],
  "changeKey": "string",
  "conversationId": "string",
  "conversationIndex": "String (binary)",
  "createdDateTime": "String (timestamp)",
  "flag": {"@odata.type": "microsoft.graph.followupFlag"},
  "from": {"@odata.type": "microsoft.graph.recipient"},
  "hasAttachments": true,
  "id": "string (identifier)",
  "importance": "String",
  "inferenceClassification": "String",
  "internetMessageHeaders": [{"@odata.type": "microsoft.graph.internetMessageHeader"}],
  "internetMessageId": "String",
  "isDeliveryReceiptRequested": true,
  "isDraft": true,
  "isRead": true,
  "isReadReceiptRequested": true,
  "lastModifiedDateTime": "String (timestamp)",
  "parentFolderId": "string",
  "receivedDateTime": "String (timestamp)",
  "replyTo": [{"@odata.type": "microsoft.graph.recipient"}],
  "sender": {"@odata.type": "microsoft.graph.recipient"},
  "sentDateTime": "String (timestamp)",
  "subject": "string",
  "toRecipients": [{"@odata.type": "microsoft.graph.recipient"}],
  "uniqueBody": {"@odata.type": "microsoft.graph.itemBody"},
  "webLink": "string",

  "attachments": [{"@odata.type": "microsoft.graph.attachment"}],
  "extensions": [{"@odata.type": "microsoft.graph.extension"}],
  "multiValueExtendedProperties": [{"@odata.type": "microsoft.graph.multiValueLegacyExtendedProperty"}],
  "singleValueExtendedProperties": [{"@odata.type": "microsoft.graph.singleValueLegacyExtendedProperty"}]
}
```

## Related content

- [Get mailbox settings](https://learn.microsoft.com/en-us/graph/api/user-get-mailboxsettings?view=graph-rest-1.0)
- [Update mailbox settings](https://learn.microsoft.com/en-us/graph/api/user-update-mailboxsettings?view=graph-rest-1.0)
- [Use delta query to track changes in Microsoft Graph data](https://learn.microsoft.com/en-us/graph/delta-query-overview)
- [Get incremental changes to messages in a folder](https://learn.microsoft.com/en-us/graph/delta-query-messages)
- [Add custom data to resources using extensions](https://learn.microsoft.com/en-us/graph/extensibility-overview)
- [Add custom data to users using open extensions](https://learn.microsoft.com/en-us/graph/extensibility-open-users)
- [Add custom data to groups using schema extensions](https://learn.microsoft.com/en-us/graph/extensibility-schema-groups)

* * *
