# checklistItem resource type

Namespace: microsoft.graph

Represents a subtask in a bigger [todoTask](https://learn.microsoft.com/en-us/graph/api/resources/todotask?view=graph-rest-1.0). **ChecklistItem** allows breaking down a complex task into more actionable, smaller tasks.

## Methods

| Method | Return type | Description |
| --- | --- | --- |
| [List](https://learn.microsoft.com/en-us/graph/api/todotask-list-checklistitems?view=graph-rest-1.0) | [checklistItem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem?view=graph-rest-1.0) collection | Get a list of the [checklistItem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem?view=graph-rest-1.0) objects and their properties. |
| [Create](https://learn.microsoft.com/en-us/graph/api/todotask-post-checklistitems?view=graph-rest-1.0) | [checklistItem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem?view=graph-rest-1.0) | Create a new [checklistItem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem?view=graph-rest-1.0) object. |
| [Get](https://learn.microsoft.com/en-us/graph/api/checklistitem-get?view=graph-rest-1.0) | [checklistItem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem?view=graph-rest-1.0) | Read the properties and relationships of a [checklistItem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem?view=graph-rest-1.0) object. |
| [Update](https://learn.microsoft.com/en-us/graph/api/checklistitem-update?view=graph-rest-1.0) | [checklistItem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem?view=graph-rest-1.0) | Update the properties of a [checklistItem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem?view=graph-rest-1.0) object. |
| [Delete](https://learn.microsoft.com/en-us/graph/api/checklistitem-delete?view=graph-rest-1.0) | None | Delete a [checklistItem](https://learn.microsoft.com/en-us/graph/api/resources/checklistitem?view=graph-rest-1.0) object. |

## Properties

| Property | Type | Description |
| --- | --- | --- |
| checkedDateTime | DateTimeOffset | The date and time when the **checklistItem** was finished. |
| createdDateTime | DateTimeOffset | The date and time when the **checklistItem** was created. |
| displayName | String | Indicates the title of the **checklistItem**. |
| id | String | Server generated ID for the the **checkListItem** |
| isChecked | Boolean | State that indicates whether the item is checked off or not. |

## Relationships

None.

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "@odata.type": "#microsoft.graph.checklistItem",
  "checkedDateTime": "String (timestamp)",
  "createdDateTime": "String (timestamp)",
  "displayName": "String",
  "id": "String (identifier)",
  "isChecked": "Boolean"
}
```

* * *
