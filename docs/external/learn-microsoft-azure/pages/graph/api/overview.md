# Microsoft Graph REST API v1.0 endpoint reference

Welcome to Microsoft Graph REST API reference for the `v1.0` endpoint.

API sets on the `v1.0` endpoint (`https://graph.microsoft.com/v1.0`) have reached general availability (GA), and have gone through a rigorous review-and-feedback process with customers to meet practical, production needs. Updates to APIs on this endpoint are additive in nature and don't break existing app scenarios.

## Common use cases

The power of Microsoft Graph lies in easy navigation of entities and relationships across different services exposed on a single Microsoft Graph REST endpoint.

Some of these services are designed to enable rich scenarios around a [user](https://learn.microsoft.com/en-us/graph/api/resources/user?view=graph-rest-1.0) and around a [group](https://learn.microsoft.com/en-us/graph/api/resources/group?view=graph-rest-1.0).

### User-centric use cases in v1.0

- [Get the profile](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0) and [photo](https://learn.microsoft.com/en-us/graph/api/resources/profilephoto?view=graph-rest-1.0) of a user.
- [Get the profile information for a user's manager](https://learn.microsoft.com/en-us/graph/api/user-list-manager?view=graph-rest-1.0) and [IDs of their direct reports](https://learn.microsoft.com/en-us/graph/api/user-list-directreports?view=graph-rest-1.0), all stored in Microsoft Entra ID.
- [Access a user's files on OneDrive](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0), find the [identity](https://learn.microsoft.com/en-us/graph/api/resources/identityset?view=graph-rest-1.0) of the last person who modified a [file](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0) there, and go to that person's profile.
- [Access a user's calendar](https://learn.microsoft.com/en-us/graph/api/calendar-get?view=graph-rest-1.0) on Exchange Online and [determine the best time to meet with their team](https://learn.microsoft.com/en-us/graph/api/user-findmeetingtimes?view=graph-rest-1.0) in the next two weeks.
- [Subscribe to](https://learn.microsoft.com/en-us/graph/api/subscription-post-subscriptions?view=graph-rest-1.0) and [track changes](https://learn.microsoft.com/en-us/graph/api/event-delta?view=graph-rest-1.0) in a user's calendar, and tell the user when they're spending more than 80% of their time in meetings.
- [Set automatic replies](https://learn.microsoft.com/en-us/graph/api/user-update-mailboxsettings?view=graph-rest-1.0#example-1) when a user is away from the office.
- [Get the people who are most relevant to a user](https://learn.microsoft.com/en-us/graph/api/user-list-people?view=graph-rest-1.0), based on communication, collaboration, and business relationships.
- Get the latest sales projection from a [chart](https://learn.microsoft.com/en-us/graph/api/resources/workbookchart?view=graph-rest-1.0) in an Excel file in a user's OneDrive.
- [Find the tasks assigned to a user in Planner](https://learn.microsoft.com/en-us/graph/api/planneruser-list-tasks?view=graph-rest-1.0).

### Microsoft 365 group use cases in v1.0

- Run a report on Microsoft 365 groups in an organization and identify the group with the most [communication among group members](https://learn.microsoft.com/en-us/graph/api/reportroot-getoffice365groupsactivitycounts?view=graph-rest-1.0).
- [Find the plans of this Microsoft 365 group](https://learn.microsoft.com/en-us/graph/api/plannergroup-list-plans?view=graph-rest-1.0), and the [assignment of tasks](https://learn.microsoft.com/en-us/graph/api/resources/plannerassignments?view=graph-rest-1.0) in that plan.
- [Start a new conversation](https://learn.microsoft.com/en-us/graph/api/group-post-conversations?view=graph-rest-1.0) in the Microsoft 365 group to determine if members want to [create another group](https://learn.microsoft.com/en-us/graph/api/group-post-groups?view=graph-rest-1.0) to share the workload.
- [Get the default notebook](https://learn.microsoft.com/en-us/graph/api/notebook-get?view=graph-rest-1.0) for the group and [create a page](https://learn.microsoft.com/en-us/graph/api/section-post-pages?view=graph-rest-1.0) to note the outcome of the investigation.

## Call the v1.0 endpoint

Microsoft Graph API requests to the v1.0 endpoint use the following pattern:

HTTP

Copy

```http
https://graph.microsoft.com/v1.0/{resource}?[query_parameters]
```

For more information about Microsoft Graph REST API calls, see [Use the Microsoft Graph API](https://learn.microsoft.com/en-us/graph/use-the-api).

## Microsoft Graph beta endpoint

Currently, two versions of Microsoft Graph REST APIs are available: v1.0 and beta.

If you're interested in new or enhanced APIs that are still in preview status, see [Microsoft Graph beta endpoint reference](https://learn.microsoft.com/en-us/graph/api/overview?view=graph-rest-beta&preserve-view=true).

Caution

APIs in preview status are subject to change, and might break existing scenarios without notice. Don't take a production dependency on APIs in the `beta` endpoint.

For more information, see [Versioning and support](https://learn.microsoft.com/en-us/graph/versioning-and-support).

## What's new

Find out [what's new](https://learn.microsoft.com/en-us/graph/whats-new-overview) in the v1.0 endpoint.

For details about changes to Microsoft Graph APIs in v1.0, explore the [API changelog](https://developer.microsoft.com/graph/changelog/?filterby=v1.0).

## Related content

- [Overview of Microsoft Graph](https://learn.microsoft.com/en-us/graph/overview)
- [Microsoft Graph Explorer](https://developer.microsoft.com/graph/graph-explorer)
- [Microsoft Graph quick start](https://developer.microsoft.com/graph/quick-start)
- [Use Microsoft Graph SDKs](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview)

* * *
