# Use delta query to track changes in Microsoft Graph data

Delta query, also called _change tracking_, enables applications to discover newly created, updated, or deleted entities without performing a full read of the target resource with every request. Microsoft Graph applications can use delta query to efficiently synchronize changes with a local data store.

Using delta query helps you avoid constantly polling Microsoft Graph, as the app requests only data that changed since the last request. This pattern allows the application to reduce the amount of data it requests, thereby reducing the cost of the request and as such, likely limit the chances of the requests being [throttled](https://learn.microsoft.com/en-us/graph/throttling).

Delta query uses a _pull_ model, where the application requests changes from Microsoft Graph; while [change notifications](https://learn.microsoft.com/en-us/graph/change-notifications-overview) use a _push_ model, where Microsoft Graph notifies the application of changes.

Important

The change tracking feature isn't supported in Microsoft Entra External ID in external tenants and Azure AD B2C tenants.

## Use delta query to track changes in a resource collection

The typical call pattern is as follows:

1. The application makes a GET request with the **delta** function on the desired resource. For example, `GET https://graph.microsoft.com/v1.0/users/delta`.

Tip

`/delta` is a shortcut for the fully qualified name `/microsoft.graph.delta`.

2. Microsoft Graph responds with the requested resource and a [state token](https://learn.microsoft.com/en-us/graph/delta-query-overview#state-tokens).

a. If Microsoft Graph returns a `@odata.nextLink` URL, there are more pages of data to retrieve in the session, even if the current response contains an empty result. The application uses the `@odata.nextLink` URL to continue making requests to retrieve all pages of data until Microsoft Graph returns a `@odata.deltaLink` URL in the response.

b. If Microsoft Graph returns a `@odata.deltaLink` URL, there's no more data about the existing state of the resource to return in the current session. For future requests, the application uses the `@odata.deltaLink` URL to learn about changes to the resource.

c. A page can't contain both `@odata.deltaLink` and `@odata.nextLink`.

The Microsoft Graph response in Step 2 includes the resources that _currently_ exist in the collection. Resources that were deleted before the initial delta query aren't returned. Updates made before the initial request are summarized on the resource returned as its latest state.

3. When the application needs to learn about changes to the resource, it uses the `@odata.deltaLink` URL it received in step 2 to make requests. The application can make this request immediately after completing step 2 or when it checks for changes.

4. Microsoft Graph returns a response describing changes to the resource since the previous request, and either a `@odata.nextLink` URL or a `@odata.deltaLink` URL.

- Microsoft Entra ID resources such as users and groups support "sync from now" scenarios. This feature allows you to skip steps 1 and 2 (if you're not interested in retrieving the full state of the resource) and ask for the latest `@odata.deltaLink` instead. Append `$deltatoken=latest` to the `delta` function and the response contains a `@odata.deltaLink` and no resource data. Resources in OneDrive and SharePoint also support this feature but require `token=latest` instead.
- `$select` and `$deltaLink` query parameters are supported for some Microsoft Entra resources so that customers can change the properties they want to track for an existing `@odata.deltaLink`. Delta queries with both `$select` and `$skiptoken` aren't supported.

### State tokens

A delta query GET response always includes a URL specified in a `@odata.nextLink` or `@odata.deltaLink` response header.
The `@odata.nextLink` URL includes a `$skiptoken`, and a `@odata.deltaLink` URL includes a `$deltatoken`.

These tokens are opaque to the client app but important as follows:

- Each token reflects the state and represents a snapshot of the resource in that round of change tracking.
- The state tokens encode and include query parameters (such as `$select`) specified in the initial delta query request. Therefore, don't modify subsequent delta query requests to repeat these query parameters.
- When carrying out delta query, you can copy and apply the `@odata.nextLink` or `@odata.deltaLink` URL to the next **delta** function call without having to inspect the contents of the URL, including its state token.

### Optional query parameters

If a client uses a query parameter, it _must_ be specified in the initial request. Microsoft Graph automatically encodes the specified query parameter into the `@odata.nextLink` or `@odata.deltaLink` in the response and in all subsequent `@odata.nextLink` or `@odata.deltaLink` URLs.

Note the general limited support of the following optional query parameters:

- `$orderby`

Don't assume a specific sequence of the responses returned from a delta query. Assume that the same item can show up anywhere in the `@odata.nextLink` sequence and handle that in your merge logic.

- `$top`

The number of objects in each page can vary depending on the resource type and the type of changes made to the resource.

For the [message](https://learn.microsoft.com/en-us/graph/api/resources/message) resource, see details for [query parameters support in a delta query](https://learn.microsoft.com/en-us/graph/delta-query-messages#use-query-parameters-in-a-delta-query-for-messages).

For the [user](https://learn.microsoft.com/en-us/graph/api/resources/user) and [group](https://learn.microsoft.com/en-us/graph/api/resources/group) resources, there are restrictions on using some query parameters:

- `$expand` isn't supported.

- `$top` isn't supported.

- `$orderby` isn't supported.

- If a `$select` query parameter is used, the parameter indicates that the client prefers to only track changes on the properties or relationships specified in the `$select` statement. If a change occurs to a property that isn't selected, the resource for which that property changed doesn't appear in the delta response after a subsequent request.

- `$select` also supports **manager** and **members** navigation properties for users and groups respectively. Selecting those properties allows tracking of changes to user's manager and group memberships.

- Scoping filters allow you to track changes to one or more specific users or groups, filtering **only by object ID**. For example, the following request returns changes for the groups matching the IDs specified in the query filter.

HTTP

Copy

```http
https://graph.microsoft.com/beta/groups/delta/?$filter=id eq '477e9fc6-5de7-4406-bb2a-7e5c83c9ae5f' or id eq '004d6a07-fe70-4b92-add5-e6e37b8acd8e'
```

## Resource representation in the delta query response

- Newly created instances of a supported resource are represented in the delta query response using their standard representation.

- Updated instances are represented by their **id** with _at least_ the updated properties, but other properties might be included.

- Relationships on users and groups are represented as annotations on the standard resource representation. These annotations use the format **propertyName@delta**. The annotations are included in the response of the initial delta query request.

  - Changes to relationships stored outside the main data store aren't supported as part of change tracking. For more information, see [Changes to properties stored outside the main data store aren't tracked](https://learn.microsoft.com/en-us/graph/delta-query-overview#changes-to-properties-stored-outside-the-main-data-store-arent-tracked).
- Removed instances are represented by their **id** and an **@removed** object. The **@removed** object might include additional information about why the instance was removed. For example, `"@removed": {"reason": "changed"}`. Possible **@removed** reasons can be `changed` or `deleted`.

  - `changed` indicates the item was deleted and can be restored from [deletedItems](https://learn.microsoft.com/en-us/graph/api/directory-deleteditems-list).

  - `deleted` indicates the item is deleted and can't be restored.

    - Items [deleted from the deletedItems store](https://learn.microsoft.com/en-us/graph/api/directory-deleteditems-delete) also show as `deleted`.

The **@removed** object can be returned in the initial delta query response and in tracked (`@odata.nextLink`) responses. For example, a deleted directory object that can still be restored from deleted items shows up as `"@removed": {"reason": "changed"}`. Clients using delta query requests should be designed to handle these objects in the responses.
- Instances [restored from deletedItems](https://learn.microsoft.com/en-us/graph/api/directory-deleteditems-list) show up as newly created instances in the delta query response.

A single entity can be contained multiple times in the response, if that entity was changed multiple times and under certain conditions. Delta queries enable your application to list all the changes, but can't ensure that entities are unified in a single response.

## Supported resources

Delta query is currently supported for the following resources. Some resources that are available in v1.0 have their corresponding **delta** functions still in preview status, as indicated.

> Note: The delta function for resources marked with an asterisk (\*) are only available on the `/beta` endpoint.

| Resource collection | API |
| --- | --- |
| [application](https://learn.microsoft.com/en-us/graph/api/resources/application) | [application: delta](https://learn.microsoft.com/en-us/graph/api/application-delta) function |
| [administrativeUnit](https://learn.microsoft.com/en-us/graph/api/resources/administrativeunit) | [administrativeUnit: delta](https://learn.microsoft.com/en-us/graph/api/administrativeunit-delta) function |
| [agentIdentityBlueprint](https://learn.microsoft.com/en-us/graph/api/resources/agentidentityblueprint) | [application: delta](https://learn.microsoft.com/en-us/graph/api/application-delta) function |
| [callRecording](https://learn.microsoft.com/en-us/graph/api/resources/callrecording) | [callRecording: delta](https://learn.microsoft.com/en-us/graph/api/callrecording-delta) function |
| [callTranscript](https://learn.microsoft.com/en-us/graph/api/resources/calltranscript) | [callTranscript: delta](https://learn.microsoft.com/en-us/graph/api/calltranscript-delta) function |
| [chatMessage](https://learn.microsoft.com/en-us/graph/api/resources/chatmessage) | [chatMessage: delta](https://learn.microsoft.com/en-us/graph/api/chatmessage-delta) function |
| [contact](https://learn.microsoft.com/en-us/graph/api/resources/contact) resource | [contact: delta](https://learn.microsoft.com/en-us/graph/api/contact-delta) function |
| [contactFolder](https://learn.microsoft.com/en-us/graph/api/resources/contactfolder) | [contactFolder: delta](https://learn.microsoft.com/en-us/graph/api/contactfolder-delta) function |
| [device](https://learn.microsoft.com/en-us/graph/api/resources/device) | [device: delta](https://learn.microsoft.com/en-us/graph/api/device-delta) function |
| [directoryRole](https://learn.microsoft.com/en-us/graph/api/resources/directoryrole) | [directoryRole: delta](https://learn.microsoft.com/en-us/graph/api/directoryrole-delta) function |
| [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryObject) | [directoryObject: delta](https://learn.microsoft.com/en-us/graph/api/directoryobject-delta) function |
| [driveItem](https://learn.microsoft.com/en-us/graph/api/resources/driveitem) 1 | [driveItem: delta](https://learn.microsoft.com/en-us/graph/api/driveitem-delta) function |
| [educationAssignment](https://learn.microsoft.com/en-us/graph/api/resources/educationassignment) | [educationAssignment: delta](https://learn.microsoft.com/en-us/graph/api/educationassignment-delta) function |
| [educationCategory](https://learn.microsoft.com/en-us/graph/api/resources/educationcategory) | [educationCategory: delta](https://learn.microsoft.com/en-us/graph/api/educationcategory-delta) function |
| [educationClass](https://learn.microsoft.com/en-us/graph/api/resources/educationclass) | [educationClass: delta](https://learn.microsoft.com/en-us/graph/api/educationclass-delta) function |
| [educationSchool](https://learn.microsoft.com/en-us/graph/api/resources/educationschool) | [educationSchool: delta](https://learn.microsoft.com/en-us/graph/api/educationschool-delta) function |
| [educationUser](https://learn.microsoft.com/en-us/graph/api/resources/educationuser) | [educationUser: delta](https://learn.microsoft.com/en-us/graph/api/educationuser-delta) function |
| [event](https://learn.microsoft.com/en-us/graph/api/resources/event) | [event: delta](https://learn.microsoft.com/en-us/graph/api/event-delta) function |
| [group](https://learn.microsoft.com/en-us/graph/api/resources/group) | [group: delta](https://learn.microsoft.com/en-us/graph/api/group-delta) function |
| [listItem](https://learn.microsoft.com/en-us/graph/api/resources/listitem) 1 | [listItem: delta](https://learn.microsoft.com/en-us/graph/api/listitem-delta) function |
| [mailboxFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailboxfolder) | [mailboxFolder: delta](https://learn.microsoft.com/en-us/graph/api/mailboxfolder-delta) function |
| [mailboxItem](https://learn.microsoft.com/en-us/graph/api/resources/mailboxitem) | [mailboxItem: delta](https://learn.microsoft.com/en-us/graph/api/mailboxitem-delta) function |
| [mailFolder](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder) | [mailFolder: delta](https://learn.microsoft.com/en-us/graph/api/mailfolder-delta) function |
| [message](https://learn.microsoft.com/en-us/graph/api/resources/message) | [message: delta](https://learn.microsoft.com/en-us/graph/api/message-delta) function |
| [orgContact](https://learn.microsoft.com/en-us/graph/api/resources/orgcontact) | [orgContact: delta](https://learn.microsoft.com/en-us/graph/api/orgcontact-delta) function |
| [oAuth2PermissionGrant](https://learn.microsoft.com/en-us/graph/api/resources/oauth2permissiongrant) | [oAuth2PermissionGrant: delta](https://learn.microsoft.com/en-us/graph/api/oauth2permissiongrant-delta) function |
| [plannerBucket](https://learn.microsoft.com/en-us/graph/api/resources/plannerbucket) \* | [plannerBucket: delta](https://learn.microsoft.com/en-us/graph/api/plannerbucket-delta) function |
| [plannerUser](https://learn.microsoft.com/en-us/graph/api/resources/planneruser) 2 | [plannerUser: delta](https://learn.microsoft.com/en-us/graph/api/planneruser-list-delta) function |
| [sites](https://learn.microsoft.com/en-us/graph/api/resources/site) | [delta](https://learn.microsoft.com/en-us/graph/api/site-delta) function of the [site](https://learn.microsoft.com/en-us/graph/api/resources/site) resource |
| [servicePrincipal](https://learn.microsoft.com/en-us/graph/api/resources/serviceprincipal) | [servicePrincipal: delta](https://learn.microsoft.com/en-us/graph/api/serviceprincipal-delta) function |
| [todoTask](https://learn.microsoft.com/en-us/graph/api/resources/todotask) | [todoTask: delta](https://learn.microsoft.com/en-us/graph/api/todotask-delta) function |
| [todoTaskList](https://learn.microsoft.com/en-us/graph/api/resources/todotasklist) | [todoTaskList: delta](https://learn.microsoft.com/en-us/graph/api/todotasklist-delta) function |
| [user](https://learn.microsoft.com/en-us/graph/api/resources/user) | [user: delta](https://learn.microsoft.com/en-us/graph/api/user-delta) function |

1 The usage pattern for OneDrive and SharePoint resources is similar to the other supported resources with some minor syntax differences. For more information about the current syntax, see
[driveItem: delta](https://learn.microsoft.com/en-us/graph/api/driveitem-delta) and [listItem: delta](https://learn.microsoft.com/en-us/graph/api/listitem-delta).

2 The usage pattern for Planner resources is similar to other supported resources with a few differences. For more information, see [planner: delta](https://learn.microsoft.com/en-us/graph/api/planneruser-list-delta).

### National clouds

Delta queries for supported resources are available for customers hosted on the public cloud, Microsoft Cloud for US Government, and Microsoft Cloud China operated by 21Vianet.

## Limitations

### Changes to properties stored outside the main data store aren't tracked

Some resources contain properties that are stored outside the main data store for the resource. For example, some properties of the [user](https://learn.microsoft.com/en-us/graph/api/resources/user) resource like **skills**, are stored in SharePoint and not Microsoft Entra ID. Currently, only the properties stored in the main data store trigger changes in the delta query; properties stored outside the main data store aren't supported as part of change tracking. Therefore, a change to any of these properties doesn't result in an object showing up in the delta query response.

For more information about properties stored outside of the main data store, see the [users](https://learn.microsoft.com/en-us/graph/api/resources/users) and [groups](https://learn.microsoft.com/en-us/graph/api/resources/groups-overview) documentation.

### Processing delays

Expect varying delays between the time a resource instance changes, and the time the tracked change is reflected in a delta query response.

Sometimes, due to replication delays, the changes to the object do not show up immediately when you select the `@odata.nextLink` or the `@odata.deltaLink`. Retry the `@odata.nextLink` or `@odata.deltaLink` after some time to retrieve the latest changes. Learn more in [Designing for eventual consistency for Microsoft Entra](https://devblogs.microsoft.com/identity/designing-for-eventual-consistency-for-microsoft-entra/).

### Replays

Your application must be prepared for replays, which occur when the same change appears in subsequent responses. While delta query makes a best effort to reduce replays, they're still possible.

### Synchronization reset

Delta query can return a response code of `410 Gone` and a **Location** header containing a request URL with an empty `$deltatoken` (same as the initial query). This status usually happens to prevent data inconsistency due to internal maintenance or migration of the target tenant, and is an indication that the application must restart with a full synchronization of the target tenant.

### Token duration

Delta tokens are only valid for a specific period before the client application needs to run a full synchronization again.

- For [directory objects](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject), the limit is seven days.
- For education objects ( **educationSchool**, **educationUser**, and **educationClass**), the limit is seven days.
- For Outlook entities ( **message**, **mailFolder**, **event**, **contact**, **contactFolder**, **todoTask**, and **todoTaskList**), the upper limit isn't fixed; it's dependent on the size of the internal delta token cache. While new delta tokens are continuously added in the cache, after the cache capacity is exceeded, the older delta tokens are deleted.

In case the token expires, the service should respond with a 40X-series error with error codes such as `syncStateNotFound`. For more information, see [Error codes in Microsoft Graph](https://learn.microsoft.com/en-us/graph/errors#code-property).

### Directory Extensions

When a change is made to a directory extension property, all directory extension properties of the same data type are returned, regardless of whether they have been changed or not.

## Combine delta query and change notifications

An app can use Microsoft Graph [change notifications](https://learn.microsoft.com/en-us/graph/change-notifications-overview) to subscribe to be notified when a specific resource changes. The application can then use delta query to request all changes since the last time it made the request.

Applications can use this strategy to nearly eliminate (only for supported resources) the need to frequently poll Microsoft Graph and process those changes to keep a local data store in sync, greatly reducing the chances for their requests to be throttled.

## Related content

- [Explore change notifications, which uses a push model to notify your app when a resource changes](https://learn.microsoft.com/en-us/graph/change-notifications-overview)

* * *
