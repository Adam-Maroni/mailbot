# event resource type

Namespace: microsoft.graph

An event in a [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) calendar, or the default calendar of a Microsoft 365 [group](https://learn.microsoft.com/en-us/graph/api/resources/group?view=graph-rest-1.0).

The maximum number of attendees included in an **event**, and the maximum number of recipients in an [eventMessage](https://learn.microsoft.com/en-us/graph/api/resources/eventmessage?view=graph-rest-1.0) sent from an Exchange Online mailbox is 500. For more information, see [sending limits](https://learn.microsoft.com/en-us/office365/servicedescriptions/exchange-online-service-description/exchange-online-limits#sending-limits).

This resource supports:

- Adding your own data to custom properties as [extensions](https://learn.microsoft.com/en-us/graph/extensibility-overview).
- Subscribing to [change notifications](https://learn.microsoft.com/en-us/graph/change-notifications-overview).
- Using [delta query](https://learn.microsoft.com/en-us/graph/delta-query-overview) to track incremental additions, deletions, and updates, by providing a [delta](https://learn.microsoft.com/en-us/graph/api/event-delta?view=graph-rest-1.0) function.

> **Note:** There are a few minor differences in the way you can interact with user calendars, group calendars, and their events:

- You can organize only user calendars in a [calendarGroup](https://learn.microsoft.com/en-us/graph/api/resources/calendargroup?view=graph-rest-1.0).
- You can add [attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0) objects to events in only user calendars, but not to events in group calendars.
- Outlook automatically accepts all meeting requests on behalf of groups. You can [accept](https://learn.microsoft.com/en-us/graph/api/event-accept?view=graph-rest-1.0), [tentatively accept](https://learn.microsoft.com/en-us/graph/api/event-tentativelyaccept?view=graph-rest-1.0), or [decline](https://learn.microsoft.com/en-us/graph/api/event-decline?view=graph-rest-1.0) meeting requests for _user_ calendars only.
- Outlook doesn't support reminders for group events. You can [snooze](https://learn.microsoft.com/en-us/graph/api/event-snoozereminder?view=graph-rest-1.0) or [dismiss](https://learn.microsoft.com/en-us/graph/api/event-dismissreminder?view=graph-rest-1.0) a [reminder](https://learn.microsoft.com/en-us/graph/api/resources/reminder?view=graph-rest-1.0) for _user_ calendars only.

## Methods

| Method | Return Type | Description |
| --- | --- | --- |
| [List](https://learn.microsoft.com/en-us/graph/api/user-list-events?view=graph-rest-1.0) | [Event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) collection | Retrieve a list of [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) objects in the user's mailbox. The list contains single instance meetings and series masters. |
| [Create](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) | Create a new event by posting to the instances collection. |
| [Get](https://learn.microsoft.com/en-us/graph/api/event-get?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) | Read properties and relationships of event object. |
| [Update](https://learn.microsoft.com/en-us/graph/api/event-update?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) | Update event object. |
| [Delete](https://learn.microsoft.com/en-us/graph/api/event-delete?view=graph-rest-1.0) | None | Delete event object. |
| [Permanently delete](https://learn.microsoft.com/en-us/graph/api/event-permanentdelete?view=graph-rest-1.0) | None | Permanently delete an event and place it in the purges folder in the recoverable Items folder in the user's mailbox. |
| [Get delta](https://learn.microsoft.com/en-us/graph/api/event-delta?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) collection | Get a set of events added, deleted, or updated in a **calendarView** (a range of events) of the user's primary calendar. |
| [Forward event](https://learn.microsoft.com/en-us/graph/api/event-forward?view=graph-rest-1.0) | None | Lets the organizer or attendee of a meeting event forward the meeting request to a new recipient. |
| [Cancel event](https://learn.microsoft.com/en-us/graph/api/event-cancel?view=graph-rest-1.0) | None | Send a cancellation message from the organizer to all the attendees and cancel the specified meeting. |
| [Accept event](https://learn.microsoft.com/en-us/graph/api/event-accept?view=graph-rest-1.0) | None | Accept the specified event in a user calendar. |
| [Tentatively accept](https://learn.microsoft.com/en-us/graph/api/event-tentativelyaccept?view=graph-rest-1.0) | None | Tentatively accept the specified event in a user calendar. |
| [Decline event](https://learn.microsoft.com/en-us/graph/api/event-decline?view=graph-rest-1.0) | None | Decline invitation to the specified event in a user calendar. |
| [Dismiss reminder](https://learn.microsoft.com/en-us/graph/api/event-dismissreminder?view=graph-rest-1.0) | None | Dismiss the reminder for the specified event in a user calendar. |
| [Snooze reminder](https://learn.microsoft.com/en-us/graph/api/event-snoozereminder?view=graph-rest-1.0) | None | Postpone a reminder for the specified event in a user calendar until a new time. |
| [List event instances](https://learn.microsoft.com/en-us/graph/api/event-list-instances?view=graph-rest-1.0) | [Event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) collection | Get a Event object collection. |
| **Attachments** |  |  |
| [List attachments](https://learn.microsoft.com/en-us/graph/api/event-list-attachments?view=graph-rest-1.0) | [Attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0) collection | Get all attachments on an event. |
| [Add attachment](https://learn.microsoft.com/en-us/graph/api/event-post-attachments?view=graph-rest-1.0) | [Attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0) | Add a new attachment to an event by posting to the attachments collection. |
| **Open extensions** |  |  |
| [Create open extension](https://learn.microsoft.com/en-us/graph/api/opentypeextension-post-opentypeextension?view=graph-rest-1.0) | [openTypeExtension](https://learn.microsoft.com/en-us/graph/api/resources/opentypeextension?view=graph-rest-1.0) | Create an open extension and add custom properties to a new or existing resource. |
| [Get open extension](https://learn.microsoft.com/en-us/graph/api/opentypeextension-get?view=graph-rest-1.0) | [openTypeExtension](https://learn.microsoft.com/en-us/graph/api/resources/opentypeextension?view=graph-rest-1.0) collection | Get an open extension identified by the extension name. |
| **Extended properties** |  |  |
| [Create single-value property](https://learn.microsoft.com/en-us/graph/api/singlevaluelegacyextendedproperty-post-singlevalueextendedproperties?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) | Create one or more single-value extended properties in a new or existing event. |
| [Get single-value property](https://learn.microsoft.com/en-us/graph/api/singlevaluelegacyextendedproperty-get?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) | Get events that contain a single-value extended property by using `$expand` or `$filter`. |
| [Create multi-value property](https://learn.microsoft.com/en-us/graph/api/multivaluelegacyextendedproperty-post-multivalueextendedproperties?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) | Create one or more multi-value extended properties in a new or existing event. |
| [Get multi-value property](https://learn.microsoft.com/en-us/graph/api/multivaluelegacyextendedproperty-get?view=graph-rest-1.0) | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) | Get an event that contains a multi-value extended property by using `$expand`. |

## Properties

| Property | Type | Description |
| --- | --- | --- |
| allowNewTimeProposals | Boolean | `true` if the meeting organizer allows invitees to propose a new time when responding; otherwise, `false`. Optional. The default is `true`. |
| attendees | [Attendee](https://learn.microsoft.com/en-us/graph/api/resources/attendee?view=graph-rest-1.0) collection | The collection of attendees for the event. |
| body | [ItemBody](https://learn.microsoft.com/en-us/graph/api/resources/itembody?view=graph-rest-1.0) | The body of the message associated with the event. It can be in HTML or text format. |
| bodyPreview | String | The preview of the message associated with the event. It's in text format. |
| cancelledOccurrences | String collection | Contains **occurrenceId** property values of canceled instances in a recurring series, if the event is the series master. Instances in a recurring series that are canceled are called canceled occurences.<br>Requires `$select` to retrieve. Only returned in a [Get](https://learn.microsoft.com/en-us/graph/api/event-get?view=graph-rest-1.0) operation that specifies the ID ( **seriesMasterId** property value) of a series master event. |
| categories | String collection | The categories associated with the event. Each category corresponds to the **displayName** property of an [outlookCategory](https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory?view=graph-rest-1.0) defined for the user. |
| changeKey | String | Identifies the version of the event object. Every time the event is changed, ChangeKey changes as well. It allows Exchange to apply changes to the correct version of the object. |
| createdDateTime | DateTimeOffset | The Timestamp type represents date and time information using ISO 8601 format and is always in UTC time. For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z` |
| end | [DateTimeTimeZone](https://learn.microsoft.com/en-us/graph/api/resources/datetimetimezone?view=graph-rest-1.0) | The date, time, and time zone that the event ends. By default, the end time is in UTC. |
| hasAttachments | Boolean | Set to true if the event has attachments. |
| hideAttendees | Boolean | When set to `true`, each attendee only sees themselves in the meeting request and meeting **Tracking** list. The default is false. |
| iCalUId | String | A unique identifier for an event across calendars. This ID is different for each occurrence in a recurring series. Read-only. |
| id | String | Unique identifier for the event. By default, this value changes when the item is moved from one container (such as a folder or calendar) to another. To change this behavior, use the `Prefer: IdType="ImmutableId"` header. See [Get immutable identifiers for Outlook resources](https://learn.microsoft.com/en-us/graph/outlook-immutable-id) for more information. Case-sensitive and read-only. |
| importance | String | The importance of the event. The possible values are: `low`, `normal`, `high`. |
| isAllDay | Boolean | Set to true if the event lasts all day. If true, regardless of whether it's a single-day or multi-day event, start, and endtime must be set to midnight and be in the same time zone. |
| isCancelled | Boolean | Set to true if the event has been canceled. |
| isDraft | Boolean | Set to true if the user has updated the meeting in Outlook but hasn't sent the updates to attendees. Set to false if all changes are sent, or if the event is an appointment without any attendees. |
| isOnlineMeeting | Boolean | `True` if this event has online meeting information (that is, **onlineMeeting** points to an [onlineMeetingInfo](https://learn.microsoft.com/en-us/graph/api/resources/onlinemeetinginfo?view=graph-rest-1.0) resource), `false` otherwise. Default is `false` ( **onlineMeeting** is `null`). Optional. <br> After you set **isOnlineMeeting** to `true`, Microsoft Graph initializes **onlineMeeting**. Subsequently, Outlook ignores any further changes to **isOnlineMeeting**, and the meeting remains available online. |
| isOrganizer | Boolean | Set to true if the calendar owner (specified by the **owner** property of the [calendar](https://learn.microsoft.com/en-us/graph/api/resources/calendar?view=graph-rest-1.0)) is the organizer of the event (specified by the **organizer** property of the **event**). It also applies if a delegate organized the event on behalf of the owner. |
| isReminderOn | Boolean | Set to true if an alert is set to remind the user of the event. |
| lastModifiedDateTime | DateTimeOffset | The Timestamp type represents date and time information using ISO 8601 format and is always in UTC time. For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z` |
| location | [Location](https://learn.microsoft.com/en-us/graph/api/resources/location?view=graph-rest-1.0) | The location of the event. |
| locations | [Location](https://learn.microsoft.com/en-us/graph/api/resources/location?view=graph-rest-1.0) collection | The locations where the event is held or attended from. The **location** and **locations** properties always correspond with each other. If you update the **location** property, any prior locations in the **locations** collection are removed and replaced by the new **location** value. |
| onlineMeeting | [OnlineMeetingInfo](https://learn.microsoft.com/en-us/graph/api/resources/onlinemeetinginfo?view=graph-rest-1.0) | Details for an attendee to join the meeting online. The default is null. Read-only. <br>After you set the **isOnlineMeeting** and **onlineMeetingProvider** properties to enable a meeting online, Microsoft Graph initializes **onlineMeeting**. When set, the meeting remains available online, and you can't change the **isOnlineMeeting**, **onlineMeetingProvider**, and **onlneMeeting** properties again. |
| onlineMeetingProvider | onlineMeetingProviderType | Represents the online meeting service provider. By default, **onlineMeetingProvider** is `unknown`. The possible values are `unknown`, `teamsForBusiness`, `skypeForBusiness`, and `skypeForConsumer`. Optional. <br> After you set **onlineMeetingProvider**, Microsoft Graph initializes **onlineMeeting**. Subsequently, you can't change **onlineMeetingProvider** again, and the meeting remains available online. |
| onlineMeetingUrl | String | A URL for an online meeting. The property is set only when an organizer specifies in Outlook that an event is an online meeting such as Skype. Read-only.<br>To access the URL to join an online meeting, use **joinUrl** which is exposed via the **onlineMeeting** property of the **event**. The **onlineMeetingUrl** property will be deprecated in the future. |
| organizer | [Recipient](https://learn.microsoft.com/en-us/graph/api/resources/recipient?view=graph-rest-1.0) | The organizer of the event. |
| originalEndTimeZone | String | The end time zone that was set when the event was created. A value of `tzone://Microsoft/Custom` indicates that a legacy custom time zone was set in desktop Outlook. |
| originalStart | DateTimeOffset | Represents the start time of an event when it's initially created as an occurrence or exception in a recurring series. This property is not returned for events that are single instances. Its date and time information is expressed in ISO 8601 format and is always in UTC. For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z` |
| originalStartTimeZone | String | The start time zone that was set when the event was created. A value of `tzone://Microsoft/Custom` indicates that a legacy custom time zone was set in desktop Outlook. |
| recurrence | [PatternedRecurrence](https://learn.microsoft.com/en-us/graph/api/resources/patternedrecurrence?view=graph-rest-1.0) | The recurrence pattern for the event. |
| reminderMinutesBeforeStart | Int32 | The number of minutes before the event start time that the reminder alert occurs. |
| responseRequested | Boolean | Default is true, which represents the organizer would like an invitee to send a response to the event. |
| responseStatus | [ResponseStatus](https://learn.microsoft.com/en-us/graph/api/resources/responsestatus?view=graph-rest-1.0) | Indicates the type of response sent in response to an event message. |
| sensitivity | String | The possible values are: `normal`, `personal`, `private`, and `confidential`. |
| seriesMasterId | String | The ID for the recurring series master item, if this event is part of a recurring series. |
| showAs | String | The status to show. The possible values are: `free`, `tentative`, `busy`, `oof`, `workingElsewhere`, `unknown`. |
| start | [DateTimeTimeZone](https://learn.microsoft.com/en-us/graph/api/resources/datetimetimezone?view=graph-rest-1.0) | The start date, time, and time zone of the event. By default, the start time is in UTC. |
| subject | String | The text of the event's subject line. |
| transactionId | String | A custom identifier specified by a client app for the server to avoid redundant [POST](https://learn.microsoft.com/en-us/graph/api/calendar-post-events?view=graph-rest-1.0) operations in case of client retries to create the same event. It's useful when low network connectivity causes the client to time out before receiving a response from the server for the client's prior create-event request. After you set **transactionId** when creating an event, you can't change **transactionId** in a subsequent update. This property is only returned in a response payload if an app has set it. Optional. |
| type | String | The event type. The possible values are: `singleInstance`, `occurrence`, `exception`, `seriesMaster`. Read-only |
| webLink | String | The URL to open the event in Outlook on the web.<br>Outlook on the web opens the event in the browser if you are signed in to your mailbox. Otherwise, Outlook on the web prompts you to sign in.<br>This URL can't be accessed from within an iFrame. |

The **webLink** property specifies a URL that opens the event in only earlier versions of Outlook on the web. The following is its URL format, with _{event-id}_ being the _**URL-encoded**_ value of the **id** property:

- For work or school accounts:
`https://outlook.office365.com/owa/?itemid={event-id}&exvsurl=1&path=/calendar/item`

- For Microsoft accounts:
`https://outlook.live.com/owa/?itemid={event-id}&exvsurl=1&path=/calendar/item`

To open the event in a current version of Outlook on the web, convert the URL to one of the following formats, and use that URL to open the event:

- For work or school accounts:
`https://outlook.office365.com/calendar/item/{event-id}`

- For Microsoft accounts:
`https://outlook.live.com/calendar/item/{event-id}`

## Relationships

| Relationship | Type | Description |
| --- | --- | --- |
| attachments | [Attachment](https://learn.microsoft.com/en-us/graph/api/resources/attachment?view=graph-rest-1.0) collection | The collection of [FileAttachment](https://learn.microsoft.com/en-us/graph/api/resources/fileattachment?view=graph-rest-1.0), [ItemAttachment](https://learn.microsoft.com/en-us/graph/api/resources/itemattachment?view=graph-rest-1.0), and [referenceAttachment](https://learn.microsoft.com/en-us/graph/api/resources/referenceattachment?view=graph-rest-1.0) attachments for the event. Navigation property. Read-only. Nullable. |
| calendar | [Calendar](https://learn.microsoft.com/en-us/graph/api/resources/calendar?view=graph-rest-1.0) | The calendar that contains the event. Navigation property. Read-only. |
| exceptionOccurrences | [event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) collection | Contains the **id** property values of the event instances that are exceptions in a recurring series.<br>Exceptions can differ from other occurrences in a recurring series, such as the subject, start or end times, or attendees. Exceptions don't include canceled occurrences.<br>Requires `$select` and `$expand` to retrieve. Only returned in a [GET](https://learn.microsoft.com/en-us/graph/api/event-get?view=graph-rest-1.0) operation that specifies the ID ( **seriesMasterId** property value) of a series master event. |
| extensions | [Extension](https://learn.microsoft.com/en-us/graph/api/resources/extension?view=graph-rest-1.0) collection | The collection of open extensions defined for the event. Nullable. |
| instances | [Event](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0) collection | The occurrences of a recurring series, if the event is a series master. This property includes occurrences that are part of the recurrence pattern, and exceptions modified, but doesn't include occurrences canceled from the series. Navigation property. Read-only. Nullable. |
| multiValueExtendedProperties | [multiValueLegacyExtendedProperty](https://learn.microsoft.com/en-us/graph/api/resources/multivaluelegacyextendedproperty?view=graph-rest-1.0) collection | The collection of multi-value extended properties defined for the event. Read-only. Nullable. |
| singleValueExtendedProperties | [singleValueLegacyExtendedProperty](https://learn.microsoft.com/en-us/graph/api/resources/singlevaluelegacyextendedproperty?view=graph-rest-1.0) collection | The collection of single-value extended properties defined for the event. Read-only. Nullable. |

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "allowNewTimeProposals": "Boolean",
  "attendees": [{"@odata.type": "microsoft.graph.attendee"}],
  "body": {"@odata.type": "microsoft.graph.itemBody"},
  "bodyPreview": "string",
  "cancelledOccurrences": ["String"],
  "categories": ["string"],
  "changeKey": "string",
  "createdDateTime": "String (timestamp)",
  "end": {"@odata.type": "microsoft.graph.dateTimeTimeZone"},
  "hasAttachments": true,
  "hideAttendees": false,
  "id": "string (identifier)",
  "importance": "String",
  "isAllDay": true,
  "isCancelled": true,
  "isDraft": false,
  "isOnlineMeeting": true,
  "isOrganizer": true,
  "isReminderOn": true,
  "lastModifiedDateTime": "String (timestamp)",
  "location": {"@odata.type": "microsoft.graph.location"},
  "locations": [{"@odata.type": "microsoft.graph.location"}],
  "onlineMeeting": {"@odata.type": "microsoft.graph.onlineMeetingInfo"},
  "onlineMeetingProvider": "string",
  "onlineMeetingUrl": "string",
  "organizer": {"@odata.type": "microsoft.graph.recipient"},
  "originalEndTimeZone": "string",
  "originalStart": "String (timestamp)",
  "originalStartTimeZone": "string",
  "recurrence": {"@odata.type": "microsoft.graph.patternedRecurrence"},
  "reminderMinutesBeforeStart": 1024,
  "responseRequested": true,
  "responseStatus": {"@odata.type": "microsoft.graph.responseStatus"},
  "sensitivity": "String",
  "seriesMasterId": "string",
  "showAs": "String",
  "start": {"@odata.type": "microsoft.graph.dateTimeTimeZone"},
  "subject": "string",
  "type": "String",
  "webLink": "string",

  "attachments": [ { "@odata.type": "microsoft.graph.attachment" } ],
  "calendar": { "@odata.type": "microsoft.graph.calendar" },
  "exceptionOccurrences": [{ "@odata.type": "microsoft.graph.event" }],
  "extensions": [ { "@odata.type": "microsoft.graph.extension" } ],
  "instances": [ { "@odata.type": "microsoft.graph.event" }],
  "singleValueExtendedProperties": [ { "@odata.type": "microsoft.graph.singleValueLegacyExtendedProperty" }],
  "multiValueExtendedProperties": [ { "@odata.type": "microsoft.graph.multiValueLegacyExtendedProperty" }]
}
```

## Related content

- [Use delta query to track changes in Microsoft Graph data](https://learn.microsoft.com/en-us/graph/delta-query-overview)
- [Get incremental changes to events in a folder](https://learn.microsoft.com/en-us/graph/delta-query-events)
- [Add custom data to resources using extensions](https://learn.microsoft.com/en-us/graph/extensibility-overview)
- [Add custom data to users using open extensions](https://learn.microsoft.com/en-us/graph/extensibility-open-users)
- [Add custom data to groups using schema extensions](https://learn.microsoft.com/en-us/graph/extensibility-schema-groups)
- [Bulk meetings C# sample](https://github.com/OfficeDev/Microsoft-Teams-Samples/blob/main/samples/graph-bulk-meetings/csharp)
- [Bulk meetings Node.js sample](https://github.com/OfficeDev/Microsoft-Teams-Samples/blob/main/samples/graph-bulk-meetings/nodejs)

* * *
