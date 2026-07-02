# Review access to security groups using access reviews APIs

The access reviews APIs in Microsoft Graph lets organizations audit and attest to the access that identities (also called _principals_) have to resources. You can use security groups to efficiently manage access to resources in your organization, like a SharePoint site with marketing playbooks. By using the access reviews API, organizations can periodically attest to principals that have access to such groups and resources.

In this tutorial, you learn how to:

- Create a recurring access review of memberships to security groups.
- Self-attest to the need to maintain access to a group.

## Prerequisites

To complete this tutorial, you need these resources and privileges:

- A working Microsoft Entra tenant with a Microsoft Entra ID P2 or Microsoft Entra ID Governance license enabled.
- Two test guests and a test security group in your tenant. The guests should be members of the group and the group should have at least one owner.
- Sign in to an API client such as [Graph Explorer](https://aka.ms/ge) to call Microsoft Graph with an account that has at least the _Identity Governance Administrator_ role.

  - \[Optional\] Open a new **incognito**, **anonymous**, or **InPrivate browser** window. You sign in later in this tutorial.
- Grant yourself the following delegated permissions: `AccessReview.ReadWrite.All`.

Review of groups governed by PIM only assigns active owners as reviewers. Eligible owners aren't included. At least one fallback reviewer is required for access review of groups governed by PIM. If there are no active owners when the review begins, the fallback reviewers are assigned the review.

## Step 1: Create an access review for the security group

### Request

In this call, replace these values:

- `eb75ccd2-59ef-48b7-8f76-cc3f33f899f4` with the ID of the security group.
- Value of **startDate** with today's date and value of **endDate** with a date five days from the start date.

The access review uses these settings:

- It's a self-attesting review as inferred when you don't specify a value for the **reviewers** property. Therefore, each group member self-attests to their need to maintain access to the group.
- The scope of the review is both direct and transitive members of the group.
- The reviewer must provide justification for why they need to maintain access to the group.
- The default decision is `Deny` when the reviewers don't respond to the access review request before the instance expires. The `Deny` decision removes the group members from the group.
- It's a one-time access review that ends after five days. Therefore, once access is granted, the user doesn't need to self-attest again within the access review period.
- The principals who are defined in the scope of the review receive email notifications and reminders prompting them to self-attest to their need to maintain access.

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_1_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/identityGovernance/accessReviews/definitions
Content-type: application/json

{
    "displayName": "One-time self-review for members of Building security",
    "descriptionForAdmins": "One-time self-review for members of Building security",
    "descriptionForReviewers": "One-time self-review for members of Building security",
    "scope": {
        "query": "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4/transitiveMembers",
        "queryType": "MicrosoftGraph"
    },
    "instanceEnumerationScope": {
        "query": "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4",
        "queryType": "MicrosoftGraph"
    },
    "settings": {
        "mailNotificationsEnabled": true,
        "reminderNotificationsEnabled": true,
        "justificationRequiredOnApproval": true,
        "defaultDecisionEnabled": true,
        "defaultDecision": "Deny",
        "instanceDurationInDays": 5,
        "autoApplyDecisionsEnabled": true,
        "recommendationsEnabled": true,
        "recurrence": {
            "pattern": null,
            "range": {
                "type": "numbered",
                "numberOfOccurrences": 0,
                "recurrenceTimeZone": null,
                "startDate": "2024-03-21",
                "endDate": "2024-03-30"
            }
        }
    }
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new AccessReviewScheduleDefinition
{
	DisplayName = "One-time self-review for members of Building security",
	DescriptionForAdmins = "One-time self-review for members of Building security",
	DescriptionForReviewers = "One-time self-review for members of Building security",
	Scope = new AccessReviewScope
	{
		AdditionalData = new Dictionary<string, object>
		{
			{
				"query" , "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4/transitiveMembers"
			},
			{
				"queryType" , "MicrosoftGraph"
			},
		},
	},
	InstanceEnumerationScope = new AccessReviewScope
	{
		AdditionalData = new Dictionary<string, object>
		{
			{
				"query" , "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4"
			},
			{
				"queryType" , "MicrosoftGraph"
			},
		},
	},
	Settings = new AccessReviewScheduleSettings
	{
		MailNotificationsEnabled = true,
		ReminderNotificationsEnabled = true,
		JustificationRequiredOnApproval = true,
		DefaultDecisionEnabled = true,
		DefaultDecision = "Deny",
		InstanceDurationInDays = 5,
		AutoApplyDecisionsEnabled = true,
		RecommendationsEnabled = true,
		Recurrence = new PatternedRecurrence
		{
			Pattern = null,
			Range = new RecurrenceRange
			{
				Type = RecurrenceRangeType.Numbered,
				NumberOfOccurrences = 0,
				RecurrenceTimeZone = null,
				StartDate = new Date(DateTime.Parse("2024-03-21")),
				EndDate = new Date(DateTime.Parse("2024-03-30")),
			},
		},
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.IdentityGovernance.AccessReviews.Definitions.PostAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewAccessReviewScheduleDefinition()
displayName := "One-time self-review for members of Building security"
requestBody.SetDisplayName(&displayName)
descriptionForAdmins := "One-time self-review for members of Building security"
requestBody.SetDescriptionForAdmins(&descriptionForAdmins)
descriptionForReviewers := "One-time self-review for members of Building security"
requestBody.SetDescriptionForReviewers(&descriptionForReviewers)
scope := graphmodels.NewAccessReviewScope()
additionalData := map[string]interface{}{
	"query" : "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4/transitiveMembers",
	"queryType" : "MicrosoftGraph",
}
scope.SetAdditionalData(additionalData)
requestBody.SetScope(scope)
instanceEnumerationScope := graphmodels.NewAccessReviewScope()
additionalData := map[string]interface{}{
	"query" : "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4",
	"queryType" : "MicrosoftGraph",
}
instanceEnumerationScope.SetAdditionalData(additionalData)
requestBody.SetInstanceEnumerationScope(instanceEnumerationScope)
settings := graphmodels.NewAccessReviewScheduleSettings()
mailNotificationsEnabled := true
settings.SetMailNotificationsEnabled(&mailNotificationsEnabled)
reminderNotificationsEnabled := true
settings.SetReminderNotificationsEnabled(&reminderNotificationsEnabled)
justificationRequiredOnApproval := true
settings.SetJustificationRequiredOnApproval(&justificationRequiredOnApproval)
defaultDecisionEnabled := true
settings.SetDefaultDecisionEnabled(&defaultDecisionEnabled)
defaultDecision := "Deny"
settings.SetDefaultDecision(&defaultDecision)
instanceDurationInDays := int32(5)
settings.SetInstanceDurationInDays(&instanceDurationInDays)
autoApplyDecisionsEnabled := true
settings.SetAutoApplyDecisionsEnabled(&autoApplyDecisionsEnabled)
recommendationsEnabled := true
settings.SetRecommendationsEnabled(&recommendationsEnabled)
recurrence := graphmodels.NewPatternedRecurrence()
pattern := null
recurrence.SetPattern(&pattern)
range := graphmodels.NewRecurrenceRange()
type := graphmodels.NUMBERED_RECURRENCERANGETYPE
range.SetType(&type)
numberOfOccurrences := int32(0)
range.SetNumberOfOccurrences(&numberOfOccurrences)
recurrenceTimeZone := null
range.SetRecurrenceTimeZone(&recurrenceTimeZone)
startDate := 2024-03-21
range.SetStartDate(&startDate)
endDate := 2024-03-30
range.SetEndDate(&endDate)
recurrence.SetRange(range)
settings.SetRecurrence(recurrence)
requestBody.SetSettings(settings)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
definitions, err := graphClient.IdentityGovernance().AccessReviews().Definitions().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

AccessReviewScheduleDefinition accessReviewScheduleDefinition = new AccessReviewScheduleDefinition();
accessReviewScheduleDefinition.setDisplayName("One-time self-review for members of Building security");
accessReviewScheduleDefinition.setDescriptionForAdmins("One-time self-review for members of Building security");
accessReviewScheduleDefinition.setDescriptionForReviewers("One-time self-review for members of Building security");
AccessReviewScope scope = new AccessReviewScope();
HashMap<String, Object> additionalData = new HashMap<String, Object>();
additionalData.put("query", "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4/transitiveMembers");
additionalData.put("queryType", "MicrosoftGraph");
scope.setAdditionalData(additionalData);
accessReviewScheduleDefinition.setScope(scope);
AccessReviewScope instanceEnumerationScope = new AccessReviewScope();
HashMap<String, Object> additionalData1 = new HashMap<String, Object>();
additionalData1.put("query", "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4");
additionalData1.put("queryType", "MicrosoftGraph");
instanceEnumerationScope.setAdditionalData(additionalData1);
accessReviewScheduleDefinition.setInstanceEnumerationScope(instanceEnumerationScope);
AccessReviewScheduleSettings settings = new AccessReviewScheduleSettings();
settings.setMailNotificationsEnabled(true);
settings.setReminderNotificationsEnabled(true);
settings.setJustificationRequiredOnApproval(true);
settings.setDefaultDecisionEnabled(true);
settings.setDefaultDecision("Deny");
settings.setInstanceDurationInDays(5);
settings.setAutoApplyDecisionsEnabled(true);
settings.setRecommendationsEnabled(true);
PatternedRecurrence recurrence = new PatternedRecurrence();
recurrence.setPattern(null);
RecurrenceRange range = new RecurrenceRange();
range.setType(RecurrenceRangeType.Numbered);
range.setNumberOfOccurrences(0);
range.setRecurrenceTimeZone(null);
LocalDate startDate = LocalDate.parse("2024-03-21");
range.setStartDate(startDate);
LocalDate endDate = LocalDate.parse("2024-03-30");
range.setEndDate(endDate);
recurrence.setRange(range);
settings.setRecurrence(recurrence);
accessReviewScheduleDefinition.setSettings(settings);
AccessReviewScheduleDefinition result = graphClient.identityGovernance().accessReviews().definitions().post(accessReviewScheduleDefinition);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const accessReviewScheduleDefinition = {
    displayName: 'One-time self-review for members of Building security',
    descriptionForAdmins: 'One-time self-review for members of Building security',
    descriptionForReviewers: 'One-time self-review for members of Building security',
    scope: {
        query: '/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4/transitiveMembers',
        queryType: 'MicrosoftGraph'
    },
    instanceEnumerationScope: {
        query: '/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4',
        queryType: 'MicrosoftGraph'
    },
    settings: {
        mailNotificationsEnabled: true,
        reminderNotificationsEnabled: true,
        justificationRequiredOnApproval: true,
        defaultDecisionEnabled: true,
        defaultDecision: 'Deny',
        instanceDurationInDays: 5,
        autoApplyDecisionsEnabled: true,
        recommendationsEnabled: true,
        recurrence: {
            pattern: null,
            range: {
                type: 'numbered',
                numberOfOccurrences: 0,
                recurrenceTimeZone: null,
                startDate: '2024-03-21',
                endDate: '2024-03-30'
            }
        }
    }
};

await client.api('/identityGovernance/accessReviews/definitions')
	.post(accessReviewScheduleDefinition);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\AccessReviewScheduleDefinition;
use Microsoft\Graph\Generated\Models\AccessReviewScope;
use Microsoft\Graph\Generated\Models\AccessReviewScheduleSettings;
use Microsoft\Graph\Generated\Models\PatternedRecurrence;
use Microsoft\Graph\Generated\Models\RecurrenceRange;
use Microsoft\Graph\Generated\Models\RecurrenceRangeType;
use Microsoft\Kiota\Abstractions\Types\Date;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new AccessReviewScheduleDefinition();
$requestBody->setDisplayName('One-time self-review for members of Building security');
$requestBody->setDescriptionForAdmins('One-time self-review for members of Building security');
$requestBody->setDescriptionForReviewers('One-time self-review for members of Building security');
$scope = new AccessReviewScope();
$additionalData = [\
	'query' => '/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4/transitiveMembers',\
	'queryType' => 'MicrosoftGraph',\
];
$scope->setAdditionalData($additionalData);
$requestBody->setScope($scope);
$instanceEnumerationScope = new AccessReviewScope();
$additionalData = [\
	'query' => '/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4',\
	'queryType' => 'MicrosoftGraph',\
];
$instanceEnumerationScope->setAdditionalData($additionalData);
$requestBody->setInstanceEnumerationScope($instanceEnumerationScope);
$settings = new AccessReviewScheduleSettings();
$settings->setMailNotificationsEnabled(true);
$settings->setReminderNotificationsEnabled(true);
$settings->setJustificationRequiredOnApproval(true);
$settings->setDefaultDecisionEnabled(true);
$settings->setDefaultDecision('Deny');
$settings->setInstanceDurationInDays(5);
$settings->setAutoApplyDecisionsEnabled(true);
$settings->setRecommendationsEnabled(true);
$settingsRecurrence = new PatternedRecurrence();
$settingsRecurrence->setPattern(null);
$settingsRecurrenceRange = new RecurrenceRange();
$settingsRecurrenceRange->setType(new RecurrenceRangeType('numbered'));
$settingsRecurrenceRange->setNumberOfOccurrences(0);
$settingsRecurrenceRange->setRecurrenceTimeZone(null);
$settingsRecurrenceRange->setStartDate(new Date('2024-03-21'));
$settingsRecurrenceRange->setEndDate(new Date('2024-03-30'));
$settingsRecurrence->setRange($settingsRecurrenceRange);
$settings->setRecurrence($settingsRecurrence);
$requestBody->setSettings($settings);

$result = $graphServiceClient->identityGovernance()->accessReviews()->definitions()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

$params = @{
	displayName = "One-time self-review for members of Building security"
	descriptionForAdmins = "One-time self-review for members of Building security"
	descriptionForReviewers = "One-time self-review for members of Building security"
	scope = @{
		query = "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4/transitiveMembers"
		queryType = "MicrosoftGraph"
	}
	instanceEnumerationScope = @{
		query = "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4"
		queryType = "MicrosoftGraph"
	}
	settings = @{
		mailNotificationsEnabled = $true
		reminderNotificationsEnabled = $true
		justificationRequiredOnApproval = $true
		defaultDecisionEnabled = $true
		defaultDecision = "Deny"
		instanceDurationInDays = 5
		autoApplyDecisionsEnabled = $true
		recommendationsEnabled = $true
		recurrence = @{
			pattern = $null
			range = @{
				type = "numbered"
				numberOfOccurrences = 0
				recurrenceTimeZone = $null
				startDate = "2024-03-21"
				endDate = "2024-03-30"
			}
		}
	}
}

New-MgIdentityGovernanceAccessReviewDefinition -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.access_review_schedule_definition import AccessReviewScheduleDefinition
from msgraph.generated.models.access_review_scope import AccessReviewScope
from msgraph.generated.models.access_review_schedule_settings import AccessReviewScheduleSettings
from msgraph.generated.models.patterned_recurrence import PatternedRecurrence
from msgraph.generated.models.recurrence_range import RecurrenceRange
from msgraph.generated.models.recurrence_range_type import RecurrenceRangeType
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = AccessReviewScheduleDefinition(
	display_name = "One-time self-review for members of Building security",
	description_for_admins = "One-time self-review for members of Building security",
	description_for_reviewers = "One-time self-review for members of Building security",
	scope = AccessReviewScope(
		additional_data = {
				"query" : "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4/transitiveMembers",
				"query_type" : "MicrosoftGraph",
		}
	),
	instance_enumeration_scope = AccessReviewScope(
		additional_data = {
				"query" : "/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4",
				"query_type" : "MicrosoftGraph",
		}
	),
	settings = AccessReviewScheduleSettings(
		mail_notifications_enabled = True,
		reminder_notifications_enabled = True,
		justification_required_on_approval = True,
		default_decision_enabled = True,
		default_decision = "Deny",
		instance_duration_in_days = 5,
		auto_apply_decisions_enabled = True,
		recommendations_enabled = True,
		recurrence = PatternedRecurrence(
			pattern = None,
			range = RecurrenceRange(
				type = RecurrenceRangeType.Numbered,
				number_of_occurrences = 0,
				recurrence_time_zone = None,
				start_date = "2024-03-21",
				end_date = "2024-03-30",
			),
		),
	),
)

result = await graph_client.identity_governance.access_reviews.definitions.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Response

The status of the access review is **NotStarted**. Retrieve the access review (GET `https://graph.microsoft.com/v1.0/identityGovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b`) to monitor the status. When its status is **InProgress**, instances are created for the access review and decisions can be posted. You can also retrieve the access review to see its full settings.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identityGovernance/accessReviews/definitions/$entity",
    "id": "2d56c364-0695-4ec6-8b92-4c1db7c80f1b",
    "displayName": "One-time self-review for members of Building security",
    "createdDateTime": null,
    "lastModifiedDateTime": null,
    "status": "NotStarted",
    "descriptionForAdmins": "One-time self-review for members of Building security",
    "descriptionForReviewers": "One-time self-review for members of Building security",
    "scope": {},
    "instanceEnumerationScope": {},
    "reviewers": [],
    "fallbackReviewers": [],
    "settings": {
        "mailNotificationsEnabled": true,
        "reminderNotificationsEnabled": true,
        "justificationRequiredOnApproval": true,
        "defaultDecisionEnabled": true,
        "defaultDecision": "Deny",
        "instanceDurationInDays": 5,
        "autoApplyDecisionsEnabled": true,
        "recommendationsEnabled": true,
        "recommendationLookBackDuration": null,
        "decisionHistoriesForReviewersEnabled": false,
        "recurrence": {
            "pattern": null,
            "range": {
                "type": "numbered",
                "numberOfOccurrences": 0,
                "recurrenceTimeZone": null,
                "startDate": "2024-03-21",
                "endDate": "2024-03-30"
            }
        },
        "applyActions": [],
        "recommendationInsightSettings": []
    },
    "stageSettings": [],
    "additionalNotificationRecipients": []
}
```

## Step 2: List instances of the access review

Once the **status** of the access review is marked as `InProgress`, run the following query to list all instances of the access review definition. Because you created a one-time access review in the previous step, the request returns only one instance with an ID like the schedule definition's ID.

### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_2_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/identityGovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/instances
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.IdentityGovernance.AccessReviews.Definitions["{accessReviewScheduleDefinition-id}"].Instances.GetAsync();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  //other-imports
)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
instances, err := graphClient.IdentityGovernance().AccessReviews().Definitions().ByAccessReviewScheduleDefinitionId("accessReviewScheduleDefinition-id").Instances().Get(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

AccessReviewInstanceCollectionResponse result = graphClient.identityGovernance().accessReviews().definitions().byAccessReviewScheduleDefinitionId("{accessReviewScheduleDefinition-id}").instances().get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let instances = await client.api('/identityGovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/instances')
	.get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->identityGovernance()->accessReviews()->definitions()->byAccessReviewScheduleDefinitionId('accessReviewScheduleDefinition-id')->instances()->get()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

Get-MgIdentityGovernanceAccessReviewDefinitionInstance -AccessReviewScheduleDefinitionId $accessReviewScheduleDefinitionId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.identity_governance.access_reviews.definitions.by_access_review_schedule_definition_id('accessReviewScheduleDefinition-id').instances.get()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Response

In this response, the **status** of the instance is `InProgress` because **startDateTime** is past and **endDateTime** is in the future. If **startDateTime** is in the future, the status is `NotStarted`. On the other hand, if **endDateTime** is in the past, the status is `Completed`.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identityGovernance/accessReviews/definitions('2d56c364-0695-4ec6-8b92-4c1db7c80f1b')/instances",
    "value": [\
        {\
            "id": "2d56c364-0695-4ec6-8b92-4c1db7c80f1b",\
            "startDateTime": "2024-03-21T17:35:25.24Z",\
            "endDateTime": "2024-03-30T08:00:00Z",\
            "status": "InProgress",\
            "scope": {\
                "@odata.type": "#microsoft.graph.accessReviewQueryScope",\
                "query": "/v1.0/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4/transitiveMembers/microsoft.graph.user",\
                "queryType": "MicrosoftGraph",\
                "queryRoot": null\
            },\
            "reviewers": [],\
            "fallbackReviewers": []\
        }\
    ]
}
```

## Step 3: Verify who was contacted for the review

You can confirm that all members of the security group were contacted to post their review decisions for this instance of the access review.

### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_3_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_3_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_3_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_3_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_3_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_3_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_3_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_3_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/identityGovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/instances/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/contactedReviewers
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.IdentityGovernance.AccessReviews.Definitions["{accessReviewScheduleDefinition-id}"].Instances["{accessReviewInstance-id}"].ContactedReviewers.GetAsync();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  //other-imports
)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
contactedReviewers, err := graphClient.IdentityGovernance().AccessReviews().Definitions().ByAccessReviewScheduleDefinitionId("accessReviewScheduleDefinition-id").Instances().ByAccessReviewInstanceId("accessReviewInstance-id").ContactedReviewers().Get(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

AccessReviewReviewerCollectionResponse result = graphClient.identityGovernance().accessReviews().definitions().byAccessReviewScheduleDefinitionId("{accessReviewScheduleDefinition-id}").instances().byAccessReviewInstanceId("{accessReviewInstance-id}").contactedReviewers().get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let contactedReviewers = await client.api('/identityGovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/instances/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/contactedReviewers')
	.get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->identityGovernance()->accessReviews()->definitions()->byAccessReviewScheduleDefinitionId('accessReviewScheduleDefinition-id')->instances()->byAccessReviewInstanceId('accessReviewInstance-id')->contactedReviewers()->get()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

Get-MgIdentityGovernanceAccessReviewDefinitionInstanceContactedReviewer -AccessReviewScheduleDefinitionId $accessReviewScheduleDefinitionId -AccessReviewInstanceId $accessReviewInstanceId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.identity_governance.access_reviews.definitions.by_access_review_schedule_definition_id('accessReviewScheduleDefinition-id').instances.by_access_review_instance_id('accessReviewInstance-id').contacted_reviewers.get()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Response

The following response shows that the two members of the security group were notified of their pending review.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identityGovernance/accessReviews/definitions('2d56c364-0695-4ec6-8b92-4c1db7c80f1b')/instances('2d56c364-0695-4ec6-8b92-4c1db7c80f1b')/contactedReviewers",
    "@odata.count": 2,
    "value": [\
        {\
            "id": "3b8ceebc-49e6-4e0c-9e14-c906374a7ef6",\
            "displayName": "Adele Vance",\
            "userPrincipalName": "AdeleV@Contoso.com",\
            "createdDateTime": "2024-03-21T17:35:34.4092545Z"\
        },\
        {\
            "id": "bf59c5ba-5304-4c9b-9192-e5a4cb8444e7",\
            "displayName": "Alex Wilber",\
            "userPrincipalName": "AlexW@Contoso.com",\
            "createdDateTime": "2024-03-21T17:35:34.4092545Z"\
        }\
    ]
}
```

## Step 4: Get decisions

You're interested in the decisions taken for the instance of the access review.

### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_4_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_4_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_4_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_4_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_4_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_4_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_4_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_4_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/identityGovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/instances/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/decisions
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.IdentityGovernance.AccessReviews.Definitions["{accessReviewScheduleDefinition-id}"].Instances["{accessReviewInstance-id}"].Decisions.GetAsync();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  //other-imports
)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
decisions, err := graphClient.IdentityGovernance().AccessReviews().Definitions().ByAccessReviewScheduleDefinitionId("accessReviewScheduleDefinition-id").Instances().ByAccessReviewInstanceId("accessReviewInstance-id").Decisions().Get(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

AccessReviewInstanceDecisionItemCollectionResponse result = graphClient.identityGovernance().accessReviews().definitions().byAccessReviewScheduleDefinitionId("{accessReviewScheduleDefinition-id}").instances().byAccessReviewInstanceId("{accessReviewInstance-id}").decisions().get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let decisions = await client.api('/identityGovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/instances/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/decisions')
	.get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->identityGovernance()->accessReviews()->definitions()->byAccessReviewScheduleDefinitionId('accessReviewScheduleDefinition-id')->instances()->byAccessReviewInstanceId('accessReviewInstance-id')->decisions()->get()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

Get-MgIdentityGovernanceAccessReviewDefinitionInstanceDecision -AccessReviewScheduleDefinitionId $accessReviewScheduleDefinitionId -AccessReviewInstanceId $accessReviewInstanceId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.identity_governance.access_reviews.definitions.by_access_review_schedule_definition_id('accessReviewScheduleDefinition-id').instances.by_access_review_instance_id('accessReviewInstance-id').decisions.get()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Response

The following response shows the decisions taken on the instance of the review. Because the security group has two members, two decision items are expected.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identityGovernance/accessReviews/definitions('2d56c364-0695-4ec6-8b92-4c1db7c80f1b')/instances('2d56c364-0695-4ec6-8b92-4c1db7c80f1b')/decisions",
    "@odata.count": 2,
    "value": [\
        {\
            "id": "4db68765-472d-4aa2-847a-433ea94bcfaf",\
            "accessReviewId": "2d56c364-0695-4ec6-8b92-4c1db7c80f1b",\
            "reviewedDateTime": null,\
            "decision": "NotReviewed",\
            "justification": "",\
            "appliedDateTime": null,\
            "applyResult": "New",\
            "recommendation": "Approve",\
            "principalLink": "https://graph.microsoft.com/v1.0/users/bf59c5ba-5304-4c9b-9192-e5a4cb8444e7",\
            "resourceLink": "https://graph.microsoft.com/v1.0/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4",\
            "reviewedBy": {\
                "id": "00000000-0000-0000-0000-000000000000",\
                "displayName": "",\
                "type": null,\
                "userPrincipalName": ""\
            },\
            "appliedBy": {\
                "id": "00000000-0000-0000-0000-000000000000",\
                "displayName": "",\
                "type": null,\
                "userPrincipalName": ""\
            },\
            "resource": {\
                "id": "eb75ccd2-59ef-48b7-8f76-cc3f33f899f4",\
                "displayName": "Building security",\
                "type": "group"\
            },\
            "principal": {\
                "@odata.type": "#microsoft.graph.userIdentity",\
                "id": "bf59c5ba-5304-4c9b-9192-e5a4cb8444e7",\
                "displayName": "Alex Wilber",\
                "type": "user",\
                "userPrincipalName": "AlexW@Contoso.com",\
                "lastUserSignInDateTime": "2/11/2022 5:31:37 PM +00:00"\
            }\
        },\
        {\
            "id": "c7de8fba-4d6a-4fab-a659-62ff0c02643d",\
            "accessReviewId": "2d56c364-0695-4ec6-8b92-4c1db7c80f1b",\
            "reviewedDateTime": null,\
            "decision": "NotReviewed",\
            "justification": "",\
            "appliedDateTime": null,\
            "applyResult": "New",\
            "recommendation": "Approve",\
            "principalLink": "https://graph.microsoft.com/v1.0/users/3b8ceebc-49e6-4e0c-9e14-c906374a7ef6",\
            "resourceLink": "https://graph.microsoft.com/v1.0/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4",\
            "reviewedBy": {\
                "id": "00000000-0000-0000-0000-000000000000",\
                "displayName": "",\
                "type": null,\
                "userPrincipalName": ""\
            },\
            "appliedBy": {\
                "id": "00000000-0000-0000-0000-000000000000",\
                "displayName": "",\
                "type": null,\
                "userPrincipalName": ""\
            },\
            "resource": {\
                "id": "eb75ccd2-59ef-48b7-8f76-cc3f33f899f4",\
                "displayName": "Building security",\
                "type": "group"\
            },\
            "principal": {\
                "@odata.type": "#microsoft.graph.userIdentity",\
                "id": "3b8ceebc-49e6-4e0c-9e14-c906374a7ef6",\
                "displayName": "Adele Vance",\
                "type": "user",\
                "userPrincipalName": "AdeleV@Contoso.com",\
                "lastUserSignInDateTime": "2/11/2022 4:58:13 PM +00:00"\
            }\
        }\
    ]
}
```

From the call, the **decision** property has the value of `NotReviewed` because the group members haven't completed their self-attestation. The next step shows how each member can self-attest to their need for access review.

## Step 5: Self-attest to a pending access decision

You configured the access review as self-attesting. This configuration requires both members of the group to self-attest to their need to maintain access to the group.

Complete this step as one of the two members of the security group.

In this step, you list your pending access reviews and complete the self-attestation process. You can complete this step in one of two ways: using the API or the [My Access portal](https://myaccess.microsoft.com/). The other reviewer doesn't self-attest, so the default decisions are applied to their access review.

Start a new **incognito**, **anonymous**, or **InPrivate browsing** browser session, and sign in as one of the two members of the security group. By doing so, you don't interrupt your current administrator session. Alternatively, you can interrupt your current administrator session by logging out of Graph Explorer and logging back in as one of the two group members.

Start a new **incognito**, **anonymous**, or **InPrivate browsing** session, and sign in as one of the two members of the security group. This way, you don't interrupt your current administrator session. Alternatively, you can log out of Graph Explorer and log back in as one of the two group members.

### Method 1: Use the access reviews APIs to self-review pending access

#### List your access reviews decision items

##### Request

HTTP

Copy

```http
GET https://graph.microsoft.com/v1.0/identitygovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/instances/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/decisions/filterByCurrentUser(on='reviewer')
```

##### Response

From the response, you (Adele Vance) have one pending access review ( **decision** is `NotReviewed`) to self-attest to. The **principal** and **resource** properties indicate the principal that the decision applies to and the resource to which access is under review. In this case, Adele Vance and the security group respectively.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#Collection(accessReviewInstanceDecisionItem)",
    "@odata.count": 1,
    "value": [\
        {\
            "@odata.type": "#microsoft.graph.accessReviewInstanceDecisionItem",\
            "id": "c7de8fba-4d6a-4fab-a659-62ff0c02643d",\
            "accessReviewId": "2d56c364-0695-4ec6-8b92-4c1db7c80f1b",\
            "reviewedDateTime": null,\
            "decision": "NotReviewed",\
            "justification": "",\
            "appliedDateTime": null,\
            "applyResult": "New",\
            "recommendation": "Approve",\
            "principalLink": "https://graph.microsoft.com/v1.0/users/3b8ceebc-49e6-4e0c-9e14-c906374a7ef6",\
            "resourceLink": "https://graph.microsoft.com/v1.0/groups/eb75ccd2-59ef-48b7-8f76-cc3f33f899f4",\
            "reviewedBy": {\
                "id": "00000000-0000-0000-0000-000000000000",\
                "displayName": "",\
                "type": null,\
                "userPrincipalName": ""\
            },\
            "appliedBy": {\
                "id": "00000000-0000-0000-0000-000000000000",\
                "displayName": "",\
                "type": null,\
                "userPrincipalName": ""\
            },\
            "resource": {\
                "id": "eb75ccd2-59ef-48b7-8f76-cc3f33f899f4",\
                "displayName": "Building security",\
                "type": "group"\
            },\
            "principal": {\
                "@odata.type": "#microsoft.graph.userIdentity",\
                "id": "3b8ceebc-49e6-4e0c-9e14-c906374a7ef6",\
                "displayName": "Adele Vance",\
                "type": "user",\
                "userPrincipalName": "AdeleV@Contoso.com",\
                "lastUserSignInDateTime": "2/15/2022 9:35:23 AM +00:00"\
            }\
        }\
    ]
}
```

#### Record a decision

To complete the access review, Adele Vance confirms the need to maintain access to the security group.

The request returns a `204 No Content` response code.

HTTP

Copy

```http
PATCH https://graph.microsoft.com/v1.0/identitygovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/instances/2d56c364-0695-4ec6-8b92-4c1db7c80f1b/decisions/c7de8fba-4d6a-4fab-a659-62ff0c02643d

{
    "decision": "Approve",
    "justification": "As the assistant security manager, I still need access to the building security group."
}
```

#### Verify the decisions

To verify the decisions that you recorded for your access review, [list your access review decision items](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#list-your-access-reviews-decision-items). While the access review period hasn't expired nor the decisions applied, the **applyResult** is marked as `New` and you can change the decision.

You can now sign out and exit the incognito browser session.

### Method 2: Use the My Access portal

Alternatively, you can check your pending access review instances through the [My Access portal](https://myaccess.microsoft.com/).

- List the pending access reviews. The user can follow one of two ways to get there:

  - Option 1: Select **Review access** button from the email notification that they received in their mail inbox. The email notification is similar to the following screenshot. This button is a direct link to the pending access review.

![Email notification to review your access.](https://learn.microsoft.com/en-us/graph/images/tutorials-identity/tutorial-access-reviews-emailnotification.png)

  - Option 2: Go to the [My Access portal](https://myaccess.microsoft.com/) portal. Select the **Access reviews** menu and select the **Groups and Apps** tab.
- From the list of access reviews, select the access review for which you want to post the decision. Select **Yes** to post the decision that you still need access to **Building security**. Enter a reason, then select **Submit**.

![Self-attest to the need to maintain access to a resource.](https://learn.microsoft.com/en-us/graph/images/tutorials-identity/tutorial-access-reviews-selfattest.png)

You can now sign out and exit the incognito browser session.

## Step 6: Confirm the decisions and the status of the access review

Back in the main browser session where you're still logged in with administrator privileges, repeat Step 4 to see that the **decision** property for Adele Vance is now `Approve`. When the access review ends or expires, the default decision of `Deny` is recorded for Alex Wilber. The decisions are then automatically applied because the **autoApplyDecisionsEnabled** was set to `true` and the period of the access review instance ended. Adele maintains access to the security group while Alex is automatically removed from the group.

Congratulations! You created an access review and self-attested to your need to maintain access. You only self-attested once and maintain your access until it's removed through either a `Deny` decision of another access review instance or another internal process.

## Step 7: Clean up resources

In this call, you delete the access review definition. Because the access review schedule definition is the blueprint for the access review, deleting the definition removes the related settings, instances, and decisions.

The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_5_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_5_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_5_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_5_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_5_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_5_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_5_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-accessreviews-securitygroup?tabs=http#tabpanel_5_python)

HTTP

Copy

```http
DELETE https://graph.microsoft.com/beta/identityGovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
await graphClient.IdentityGovernance.AccessReviews.Definitions["{accessReviewScheduleDefinition-id}"].DeleteAsync();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v0.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-beta-sdk-go"
	  //other-imports
)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
graphClient.IdentityGovernance().AccessReviews().Definitions().ByAccessReviewScheduleDefinitionId("accessReviewScheduleDefinition-id").Delete(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

graphClient.identityGovernance().accessReviews().definitions().byAccessReviewScheduleDefinitionId("{accessReviewScheduleDefinition-id}").delete();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

await client.api('/identityGovernance/accessReviews/definitions/2d56c364-0695-4ec6-8b92-4c1db7c80f1b')
	.version('beta')
	.delete();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\Beta\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$graphServiceClient->identityGovernance()->accessReviews()->definitions()->byAccessReviewScheduleDefinitionId('accessReviewScheduleDefinition-id')->delete()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Beta.Identity.Governance

Remove-MgBetaIdentityGovernanceAccessReviewDefinition -AccessReviewScheduleDefinitionId $accessReviewScheduleDefinitionId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph_beta import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

await graph_client.identity_governance.access_reviews.definitions.by_access_review_schedule_definition_id('accessReviewScheduleDefinition-id').delete()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

## Conclusion

You created an access review in which the principals self-attested to their need to maintain their access to a resource, in this case, the **Building security** group.

This tutorial demonstrated one of the automation scenarios for the Microsoft Entra access reviews APIs. The APIs support different scenarios through a combination of resources, principals, and reviewers to suit your access attestation needs. For more information, see the [access reviews API](https://learn.microsoft.com/en-us/graph/api/resources/accessreviewsv2-overview).

## Related content

- [What are Microsoft Entra access reviews?](https://learn.microsoft.com/en-us/entra/id-governance/access-reviews-overview)
- [Tutorial: Review access for yourself to groups or applications in access reviews using the Microsoft Entra admin center](https://learn.microsoft.com/en-us/entra/id-governance/review-your-access)
- [How to configure the scope of your access review using access reviews APIs](https://learn.microsoft.com/en-us/graph/accessreviews-scope-concept)

* * *
