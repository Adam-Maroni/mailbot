# Automate employee offboarding tasks after their last day of work using Lifecycle Workflows APIs

This tutorial provides step-by-step guidance for configuring offboarding tasks for employees after their last day of work using Lifecycle Workflows APIs. In this scenario, the employee termination is scheduled, possibly including a notice period. See [Complete employee offboarding tasks in real-time on their last day of work using Lifecycle Workflows APIs](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-offboard-custom-workflow) for an unscheduled, real-time termination scenario.

In this tutorial, you learn how to:

- Configure a lifecycle workflow to check for employees in a specific department, days after their last day of work.
- Configure a task to run the following tasks in sequence:
  - Remove all licenses for user
  - Remove user from all Teams
  - Delete user account
- Monitor the status of the workflow and its associated tasks.

## Prerequisites

To complete this tutorial, you need the following resources and privileges:

- This feature requires Microsoft Entra ID Governance licenses. To find the right license for your requirements, see [Microsoft Entra ID Governance licensing fundamentals](https://learn.microsoft.com/en-us/entra/id-governance/licensing-fundamentals).
- Sign in to an API client such as [Graph Explorer](https://aka.ms/ge) to call Microsoft Graph with an account that has at least the _Lifecycle Administrator_ Microsoft Entra role.
- Grant yourself the _LifecycleWorkflows.ReadWrite.All_ Microsoft Graph delegated permission.
- Create a test user account to represent an employee leaving your organization. This test user account is deleted when the workflow runs. Assign licenses and Teams memberships to the test user account.

## Create a "leaver" workflow

### Request

The following request creates an offboarding workflow with these settings:

- It can run on-demand but not on schedule. This step lets us validate the workflow using the test user's account. The workflow is updated to run on schedule later in this tutorial.
- The workflow runs seven days after the employee's [employeeLeaveDateTime](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-set-employeeleavedatetime?tabs=http) if the employee is in the "Marketing" department.
- Three workflow tasks run in sequence: the user is unassigned all licenses, removed from all teams, and then their user account is deleted.

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_1_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/identityGovernance/LifecycleWorkflows/workflows
Content-type: application/json

{
    "category": "leaver",
    "displayName": "Post-Offboarding of an employee",
    "description": "Configure offboarding tasks for employees after their last day of work",
    "isEnabled": true,
    "isSchedulingEnabled": false,
    "executionConditions": {
        "@odata.type": "#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions",
        "scope": {
            "@odata.type": "#microsoft.graph.identityGovernance.ruleBasedSubjectSet",
            "rule": "department eq 'Marketing'"
        },
        "trigger": {
            "@odata.type": "#microsoft.graph.identityGovernance.timeBasedAttributeTrigger",
            "timeBasedAttribute": "employeeLeaveDateTime",
            "offsetInDays": 7
        }
    },
    "tasks": [\
        {\
            "category": "leaver",\
            "continueOnError": false,\
            "description": "Remove all licenses assigned to the user",\
            "displayName": "Remove all licenses for user",\
            "executionSequence": 1,\
            "isEnabled": true,\
            "taskDefinitionId": "8fa97d28-3e52-4985-b3a9-a1126f9b8b4e",\
            "arguments": []\
        },\
        {\
            "category": "leaver",\
            "continueOnError": false,\
            "description": "Remove user from all Teams memberships",\
            "displayName": "Remove user from all Teams",\
            "executionSequence": 2,\
            "isEnabled": true,\
            "taskDefinitionId": "81f7b200-2816-4b3b-8c5d-dc556f07b024",\
            "arguments": []\
        },\
        {\
            "category": "leaver",\
            "continueOnError": false,\
            "description": "Delete user account in Azure AD",\
            "displayName": "Delete User Account",\
            "executionSequence": 3,\
            "isEnabled": true,\
            "taskDefinitionId": "8d18588d-9ad3-4c0f-99d0-ec215f0e3dff",\
            "arguments": []\
        }\
    ]
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models.IdentityGovernance;
using Microsoft.Graph.Models;

var requestBody = new Workflow
{
	Category = LifecycleWorkflowCategory.Leaver,
	DisplayName = "Post-Offboarding of an employee",
	Description = "Configure offboarding tasks for employees after their last day of work",
	IsEnabled = true,
	IsSchedulingEnabled = false,
	ExecutionConditions = new TriggerAndScopeBasedConditions
	{
		OdataType = "#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions",
		Scope = new RuleBasedSubjectSet
		{
			OdataType = "#microsoft.graph.identityGovernance.ruleBasedSubjectSet",
			Rule = "department eq 'Marketing'",
		},
		Trigger = new TimeBasedAttributeTrigger
		{
			OdataType = "#microsoft.graph.identityGovernance.timeBasedAttributeTrigger",
			TimeBasedAttribute = WorkflowTriggerTimeBasedAttribute.EmployeeLeaveDateTime,
			OffsetInDays = 7,
		},
	},
	Tasks = new List<TaskObject>
	{
		new TaskObject
		{
			Category = LifecycleTaskCategory.Leaver,
			ContinueOnError = false,
			Description = "Remove all licenses assigned to the user",
			DisplayName = "Remove all licenses for user",
			ExecutionSequence = 1,
			IsEnabled = true,
			TaskDefinitionId = "8fa97d28-3e52-4985-b3a9-a1126f9b8b4e",
			Arguments = new List<KeyValuePair>
			{
			},
		},
		new TaskObject
		{
			Category = LifecycleTaskCategory.Leaver,
			ContinueOnError = false,
			Description = "Remove user from all Teams memberships",
			DisplayName = "Remove user from all Teams",
			ExecutionSequence = 2,
			IsEnabled = true,
			TaskDefinitionId = "81f7b200-2816-4b3b-8c5d-dc556f07b024",
			Arguments = new List<KeyValuePair>
			{
			},
		},
		new TaskObject
		{
			Category = LifecycleTaskCategory.Leaver,
			ContinueOnError = false,
			Description = "Delete user account in Azure AD",
			DisplayName = "Delete User Account",
			ExecutionSequence = 3,
			IsEnabled = true,
			TaskDefinitionId = "8d18588d-9ad3-4c0f-99d0-ec215f0e3dff",
			Arguments = new List<KeyValuePair>
			{
			},
		},
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.IdentityGovernance.LifecycleWorkflows.Workflows.PostAsync(requestBody);
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
	  graphmodelsidentitygovernance "github.com/microsoftgraph/msgraph-sdk-go/models/identitygovernance"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodelsidentitygovernance.NewWorkflow()
category := graphmodels.LEAVER_LIFECYCLEWORKFLOWCATEGORY
requestBody.SetCategory(&category)
displayName := "Post-Offboarding of an employee"
requestBody.SetDisplayName(&displayName)
description := "Configure offboarding tasks for employees after their last day of work"
requestBody.SetDescription(&description)
isEnabled := true
requestBody.SetIsEnabled(&isEnabled)
isSchedulingEnabled := false
requestBody.SetIsSchedulingEnabled(&isSchedulingEnabled)
executionConditions := graphmodelsidentitygovernance.NewTriggerAndScopeBasedConditions()
scope := graphmodelsidentitygovernance.NewRuleBasedSubjectSet()
rule := "department eq 'Marketing'"
scope.SetRule(&rule)
executionConditions.SetScope(scope)
trigger := graphmodelsidentitygovernance.NewTimeBasedAttributeTrigger()
timeBasedAttribute := graphmodels.EMPLOYEELEAVEDATETIME_WORKFLOWTRIGGERTIMEBASEDATTRIBUTE
trigger.SetTimeBasedAttribute(&timeBasedAttribute)
offsetInDays := int32(7)
trigger.SetOffsetInDays(&offsetInDays)
executionConditions.SetTrigger(trigger)
requestBody.SetExecutionConditions(executionConditions)

task := graphmodelsidentitygovernance.NewTask()
category := graphmodels.LEAVER_LIFECYCLETASKCATEGORY
task.SetCategory(&category)
continueOnError := false
task.SetContinueOnError(&continueOnError)
description := "Remove all licenses assigned to the user"
task.SetDescription(&description)
displayName := "Remove all licenses for user"
task.SetDisplayName(&displayName)
executionSequence := int32(1)
task.SetExecutionSequence(&executionSequence)
isEnabled := true
task.SetIsEnabled(&isEnabled)
taskDefinitionId := "8fa97d28-3e52-4985-b3a9-a1126f9b8b4e"
task.SetTaskDefinitionId(&taskDefinitionId)
arguments := []graphmodels.KeyValuePairable {

}
task.SetArguments(arguments)
task1 := graphmodelsidentitygovernance.NewTask()
category := graphmodels.LEAVER_LIFECYCLETASKCATEGORY
task1.SetCategory(&category)
continueOnError := false
task1.SetContinueOnError(&continueOnError)
description := "Remove user from all Teams memberships"
task1.SetDescription(&description)
displayName := "Remove user from all Teams"
task1.SetDisplayName(&displayName)
executionSequence := int32(2)
task1.SetExecutionSequence(&executionSequence)
isEnabled := true
task1.SetIsEnabled(&isEnabled)
taskDefinitionId := "81f7b200-2816-4b3b-8c5d-dc556f07b024"
task1.SetTaskDefinitionId(&taskDefinitionId)
arguments := []graphmodels.KeyValuePairable {

}
task1.SetArguments(arguments)
task2 := graphmodelsidentitygovernance.NewTask()
category := graphmodels.LEAVER_LIFECYCLETASKCATEGORY
task2.SetCategory(&category)
continueOnError := false
task2.SetContinueOnError(&continueOnError)
description := "Delete user account in Azure AD"
task2.SetDescription(&description)
displayName := "Delete User Account"
task2.SetDisplayName(&displayName)
executionSequence := int32(3)
task2.SetExecutionSequence(&executionSequence)
isEnabled := true
task2.SetIsEnabled(&isEnabled)
taskDefinitionId := "8d18588d-9ad3-4c0f-99d0-ec215f0e3dff"
task2.SetTaskDefinitionId(&taskDefinitionId)
arguments := []graphmodels.KeyValuePairable {

}
task2.SetArguments(arguments)

tasks := []graphmodelsidentitygovernance.Taskable {
	task,
	task1,
	task2,
}
requestBody.SetTasks(tasks)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
workflows, err := graphClient.IdentityGovernance().LifecycleWorkflows().Workflows().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.identitygovernance.Workflow workflow = new com.microsoft.graph.models.identitygovernance.Workflow();
workflow.setCategory(com.microsoft.graph.models.identitygovernance.LifecycleWorkflowCategory.Leaver);
workflow.setDisplayName("Post-Offboarding of an employee");
workflow.setDescription("Configure offboarding tasks for employees after their last day of work");
workflow.setIsEnabled(true);
workflow.setIsSchedulingEnabled(false);
com.microsoft.graph.models.identitygovernance.TriggerAndScopeBasedConditions executionConditions = new com.microsoft.graph.models.identitygovernance.TriggerAndScopeBasedConditions();
executionConditions.setOdataType("#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions");
com.microsoft.graph.models.identitygovernance.RuleBasedSubjectSet scope = new com.microsoft.graph.models.identitygovernance.RuleBasedSubjectSet();
scope.setOdataType("#microsoft.graph.identityGovernance.ruleBasedSubjectSet");
scope.setRule("department eq 'Marketing'");
executionConditions.setScope(scope);
com.microsoft.graph.models.identitygovernance.TimeBasedAttributeTrigger trigger = new com.microsoft.graph.models.identitygovernance.TimeBasedAttributeTrigger();
trigger.setOdataType("#microsoft.graph.identityGovernance.timeBasedAttributeTrigger");
trigger.setTimeBasedAttribute(com.microsoft.graph.models.identitygovernance.WorkflowTriggerTimeBasedAttribute.EmployeeLeaveDateTime);
trigger.setOffsetInDays(7);
executionConditions.setTrigger(trigger);
workflow.setExecutionConditions(executionConditions);
LinkedList<com.microsoft.graph.models.identitygovernance.Task> tasks = new LinkedList<com.microsoft.graph.models.identitygovernance.Task>();
com.microsoft.graph.models.identitygovernance.Task task = new com.microsoft.graph.models.identitygovernance.Task();
task.setCategory(EnumSet.of(com.microsoft.graph.models.identitygovernance.LifecycleTaskCategory.Leaver));
task.setContinueOnError(false);
task.setDescription("Remove all licenses assigned to the user");
task.setDisplayName("Remove all licenses for user");
task.setExecutionSequence(1);
task.setIsEnabled(true);
task.setTaskDefinitionId("8fa97d28-3e52-4985-b3a9-a1126f9b8b4e");
LinkedList<KeyValuePair> arguments = new LinkedList<KeyValuePair>();
task.setArguments(arguments);
tasks.add(task);
com.microsoft.graph.models.identitygovernance.Task task1 = new com.microsoft.graph.models.identitygovernance.Task();
task1.setCategory(EnumSet.of(com.microsoft.graph.models.identitygovernance.LifecycleTaskCategory.Leaver));
task1.setContinueOnError(false);
task1.setDescription("Remove user from all Teams memberships");
task1.setDisplayName("Remove user from all Teams");
task1.setExecutionSequence(2);
task1.setIsEnabled(true);
task1.setTaskDefinitionId("81f7b200-2816-4b3b-8c5d-dc556f07b024");
LinkedList<KeyValuePair> arguments1 = new LinkedList<KeyValuePair>();
task1.setArguments(arguments1);
tasks.add(task1);
com.microsoft.graph.models.identitygovernance.Task task2 = new com.microsoft.graph.models.identitygovernance.Task();
task2.setCategory(EnumSet.of(com.microsoft.graph.models.identitygovernance.LifecycleTaskCategory.Leaver));
task2.setContinueOnError(false);
task2.setDescription("Delete user account in Azure AD");
task2.setDisplayName("Delete User Account");
task2.setExecutionSequence(3);
task2.setIsEnabled(true);
task2.setTaskDefinitionId("8d18588d-9ad3-4c0f-99d0-ec215f0e3dff");
LinkedList<KeyValuePair> arguments2 = new LinkedList<KeyValuePair>();
task2.setArguments(arguments2);
tasks.add(task2);
workflow.setTasks(tasks);
com.microsoft.graph.models.identitygovernance.Workflow result = graphClient.identityGovernance().lifecycleWorkflows().workflows().post(workflow);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const workflow = {
    category: 'leaver',
    displayName: 'Post-Offboarding of an employee',
    description: 'Configure offboarding tasks for employees after their last day of work',
    isEnabled: true,
    isSchedulingEnabled: false,
    executionConditions: {
        '@odata.type': '#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions',
        scope: {
            '@odata.type': '#microsoft.graph.identityGovernance.ruleBasedSubjectSet',
            rule: 'department eq \'Marketing\''
        },
        trigger: {
            '@odata.type': '#microsoft.graph.identityGovernance.timeBasedAttributeTrigger',
            timeBasedAttribute: 'employeeLeaveDateTime',
            offsetInDays: 7
        }
    },
    tasks: [\
        {\
            category: 'leaver',\
            continueOnError: false,\
            description: 'Remove all licenses assigned to the user',\
            displayName: 'Remove all licenses for user',\
            executionSequence: 1,\
            isEnabled: true,\
            taskDefinitionId: '8fa97d28-3e52-4985-b3a9-a1126f9b8b4e',\
            arguments: []\
        },\
        {\
            category: 'leaver',\
            continueOnError: false,\
            description: 'Remove user from all Teams memberships',\
            displayName: 'Remove user from all Teams',\
            executionSequence: 2,\
            isEnabled: true,\
            taskDefinitionId: '81f7b200-2816-4b3b-8c5d-dc556f07b024',\
            arguments: []\
        },\
        {\
            category: 'leaver',\
            continueOnError: false,\
            description: 'Delete user account in Azure AD',\
            displayName: 'Delete User Account',\
            executionSequence: 3,\
            isEnabled: true,\
            taskDefinitionId: '8d18588d-9ad3-4c0f-99d0-ec215f0e3dff',\
            arguments: []\
        }\
    ]
};

await client.api('/identityGovernance/LifecycleWorkflows/workflows')
	.post(workflow);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\IdentityGovernance\Workflow;
use Microsoft\Graph\Generated\Models\IdentityGovernance\LifecycleWorkflowCategory;
use Microsoft\Graph\Generated\Models\IdentityGovernance\TriggerAndScopeBasedConditions;
use Microsoft\Graph\Generated\Models\IdentityGovernance\RuleBasedSubjectSet;
use Microsoft\Graph\Generated\Models\IdentityGovernance\TimeBasedAttributeTrigger;
use Microsoft\Graph\Generated\Models\IdentityGovernance\WorkflowTriggerTimeBasedAttribute;
use Microsoft\Graph\Generated\Models\IdentityGovernance\Task;
use Microsoft\Graph\Generated\Models\IdentityGovernance\LifecycleTaskCategory;
use Microsoft\Graph\Generated\Models\KeyValuePair;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new Workflow();
$requestBody->setCategory(new LifecycleWorkflowCategory('leaver'));
$requestBody->setDisplayName('Post-Offboarding of an employee');
$requestBody->setDescription('Configure offboarding tasks for employees after their last day of work');
$requestBody->setIsEnabled(true);
$requestBody->setIsSchedulingEnabled(false);
$executionConditions = new TriggerAndScopeBasedConditions();
$executionConditions->setOdataType('#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions');
$executionConditionsScope = new RuleBasedSubjectSet();
$executionConditionsScope->setOdataType('#microsoft.graph.identityGovernance.ruleBasedSubjectSet');
$executionConditionsScope->setRule('department eq \'Marketing\'');
$executionConditions->setScope($executionConditionsScope);
$executionConditionsTrigger = new TimeBasedAttributeTrigger();
$executionConditionsTrigger->setOdataType('#microsoft.graph.identityGovernance.timeBasedAttributeTrigger');
$executionConditionsTrigger->setTimeBasedAttribute(new WorkflowTriggerTimeBasedAttribute('employeeLeaveDateTime'));
$executionConditionsTrigger->setOffsetInDays(7);
$executionConditions->setTrigger($executionConditionsTrigger);
$requestBody->setExecutionConditions($executionConditions);
$tasksTask1 = new Task();
$tasksTask1->setCategory(new LifecycleTaskCategory('leaver'));
$tasksTask1->setContinueOnError(false);
$tasksTask1->setDescription('Remove all licenses assigned to the user');
$tasksTask1->setDisplayName('Remove all licenses for user');
$tasksTask1->setExecutionSequence(1);
$tasksTask1->setIsEnabled(true);
$tasksTask1->setTaskDefinitionId('8fa97d28-3e52-4985-b3a9-a1126f9b8b4e');
$tasksTask1->setArguments([	]);
$tasksArray []= $tasksTask1;
$tasksTask2 = new Task();
$tasksTask2->setCategory(new LifecycleTaskCategory('leaver'));
$tasksTask2->setContinueOnError(false);
$tasksTask2->setDescription('Remove user from all Teams memberships');
$tasksTask2->setDisplayName('Remove user from all Teams');
$tasksTask2->setExecutionSequence(2);
$tasksTask2->setIsEnabled(true);
$tasksTask2->setTaskDefinitionId('81f7b200-2816-4b3b-8c5d-dc556f07b024');
$tasksTask2->setArguments([	]);
$tasksArray []= $tasksTask2;
$tasksTask3 = new Task();
$tasksTask3->setCategory(new LifecycleTaskCategory('leaver'));
$tasksTask3->setContinueOnError(false);
$tasksTask3->setDescription('Delete user account in Azure AD');
$tasksTask3->setDisplayName('Delete User Account');
$tasksTask3->setExecutionSequence(3);
$tasksTask3->setIsEnabled(true);
$tasksTask3->setTaskDefinitionId('8d18588d-9ad3-4c0f-99d0-ec215f0e3dff');
$tasksTask3->setArguments([	]);
$tasksArray []= $tasksTask3;
$requestBody->setTasks($tasksArray);

$result = $graphServiceClient->identityGovernance()->lifecycleWorkflows()->workflows()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

$params = @{
	category = "leaver"
	displayName = "Post-Offboarding of an employee"
	description = "Configure offboarding tasks for employees after their last day of work"
	isEnabled = $true
	isSchedulingEnabled = $false
	executionConditions = @{
		"@odata.type" = "#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions"
		scope = @{
			"@odata.type" = "#microsoft.graph.identityGovernance.ruleBasedSubjectSet"
			rule = "department eq 'Marketing'"
		}
		trigger = @{
			"@odata.type" = "#microsoft.graph.identityGovernance.timeBasedAttributeTrigger"
			timeBasedAttribute = "employeeLeaveDateTime"
			offsetInDays =
		}
	}
	tasks = @(
		@{
			category = "leaver"
			continueOnError = $false
			description = "Remove all licenses assigned to the user"
			displayName = "Remove all licenses for user"
			executionSequence = 1
			isEnabled = $true
			taskDefinitionId = "8fa97d28-3e52-4985-b3a9-a1126f9b8b4e"
			arguments = @(
			)
		}
		@{
			category = "leaver"
			continueOnError = $false
			description = "Remove user from all Teams memberships"
			displayName = "Remove user from all Teams"
			executionSequence = 2
			isEnabled = $true
			taskDefinitionId = "81f7b200-2816-4b3b-8c5d-dc556f07b024"
			arguments = @(
			)
		}
		@{
			category = "leaver"
			continueOnError = $false
			description = "Delete user account in Azure AD"
			displayName = "Delete User Account"
			executionSequence = 3
			isEnabled = $true
			taskDefinitionId = "8d18588d-9ad3-4c0f-99d0-ec215f0e3dff"
			arguments = @(
			)
		}
	)
}

New-MgIdentityGovernanceLifecycleWorkflow -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.identity_governance.workflow import Workflow
from msgraph.generated.models.lifecycle_workflow_category import LifecycleWorkflowCategory
from msgraph.generated.models.identity_governance.trigger_and_scope_based_conditions import TriggerAndScopeBasedConditions
from msgraph.generated.models.identity_governance.rule_based_subject_set import RuleBasedSubjectSet
from msgraph.generated.models.identity_governance.time_based_attribute_trigger import TimeBasedAttributeTrigger
from msgraph.generated.models.workflow_trigger_time_based_attribute import WorkflowTriggerTimeBasedAttribute
from msgraph.generated.models.identity_governance.task import Task
from msgraph.generated.models.lifecycle_task_category import LifecycleTaskCategory
from msgraph.generated.models.key_value_pair import KeyValuePair
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = Workflow(
	category = LifecycleWorkflowCategory.Leaver,
	display_name = "Post-Offboarding of an employee",
	description = "Configure offboarding tasks for employees after their last day of work",
	is_enabled = True,
	is_scheduling_enabled = False,
	execution_conditions = TriggerAndScopeBasedConditions(
		odata_type = "#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions",
		scope = RuleBasedSubjectSet(
			odata_type = "#microsoft.graph.identityGovernance.ruleBasedSubjectSet",
			rule = "department eq 'Marketing'",
		),
		trigger = TimeBasedAttributeTrigger(
			odata_type = "#microsoft.graph.identityGovernance.timeBasedAttributeTrigger",
			time_based_attribute = WorkflowTriggerTimeBasedAttribute.EmployeeLeaveDateTime,
			offset_in_days = 7,
		),
	),
	tasks = [\
		Task(\
			category = LifecycleTaskCategory.Leaver,\
			continue_on_error = False,\
			description = "Remove all licenses assigned to the user",\
			display_name = "Remove all licenses for user",\
			execution_sequence = 1,\
			is_enabled = True,\
			task_definition_id = "8fa97d28-3e52-4985-b3a9-a1126f9b8b4e",\
			arguments = [\
			],\
		),\
		Task(\
			category = LifecycleTaskCategory.Leaver,\
			continue_on_error = False,\
			description = "Remove user from all Teams memberships",\
			display_name = "Remove user from all Teams",\
			execution_sequence = 2,\
			is_enabled = True,\
			task_definition_id = "81f7b200-2816-4b3b-8c5d-dc556f07b024",\
			arguments = [\
			],\
		),\
		Task(\
			category = LifecycleTaskCategory.Leaver,\
			continue_on_error = False,\
			description = "Delete user account in Azure AD",\
			display_name = "Delete User Account",\
			execution_sequence = 3,\
			is_enabled = True,\
			task_definition_id = "8d18588d-9ad3-4c0f-99d0-ec215f0e3dff",\
			arguments = [\
			],\
		),\
	],
)

result = await graph_client.identity_governance.lifecycle_workflows.workflows.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Response

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identityGovernance/lifecycleWorkflows/workflows/$entity",
    "category": "leaver",
    "description": "Configure offboarding tasks for employees after their last day of work",
    "displayName": "Post-Offboarding of an employee",
    "lastModifiedDateTime": "2024-03-03T18:29:10.8412536Z",
    "createdDateTime": "2024-03-03T18:29:10.8412352Z",
    "deletedDateTime": null,
    "id": "15239232-66ed-445b-8292-2f5bbb2eb833",
    "isEnabled": true,
    "isSchedulingEnabled": false,
    "nextScheduleRunDateTime": null,
    "version": 1,
    "executionConditions": {
        "@odata.type": "#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions",
        "scope": {
            "@odata.type": "#microsoft.graph.identityGovernance.ruleBasedSubjectSet",
            "rule": "department eq 'Marketing'"
        },
        "trigger": {
            "@odata.type": "#microsoft.graph.identityGovernance.timeBasedAttributeTrigger",
            "timeBasedAttribute": "employeeLeaveDateTime",
            "offsetInDays": 7
        }
    }
}
```

## Run the workflow

Because the workflow isn't scheduled to run, you must run it manually, on-demand. In this request, the user targeted by the workflow is identified by ID `df744d9e-2148-4922-88a8-633896c1e929`.

When you run a workflow on demand, the tasks execute regardless of whether the user state matches the scope and trigger execution conditions. Therefore, even if the user isn't in the "Marketing" department or their **employeeLeaveDateTime** is set to `null`, this command still runs the tasks defined in the workflow for the user.

The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_2_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/identityGovernance/LifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833/activate

{
    "subjects": [\
        {\
            "id": "df744d9e-2148-4922-88a8-633896c1e929"\
        }\
    ]
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.IdentityGovernance.LifecycleWorkflows.Workflows.Item.MicrosoftGraphIdentityGovernanceActivate;
using Microsoft.Graph.Models;

var requestBody = new ActivatePostRequestBody
{
	Subjects = new List<User>
	{
		new User
		{
			Id = "df744d9e-2148-4922-88a8-633896c1e929",
		},
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
await graphClient.IdentityGovernance.LifecycleWorkflows.Workflows["{workflow-id}"].MicrosoftGraphIdentityGovernanceActivate.PostAsync(requestBody);
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
	  graphidentitygovernance "github.com/microsoftgraph/msgraph-sdk-go/identitygovernance"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphidentitygovernance.NewActivatePostRequestBody()

user := graphmodels.NewUser()
id := "df744d9e-2148-4922-88a8-633896c1e929"
user.SetId(&id)

subjects := []graphmodels.Userable {
	user,
}
requestBody.SetSubjects(subjects)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
graphClient.IdentityGovernance().LifecycleWorkflows().Workflows().ByWorkflowId("workflow-id").MicrosoftGraphIdentityGovernanceActivate().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.identitygovernance.lifecycleworkflows.workflows.item.microsoftgraphidentitygovernanceactivate.ActivatePostRequestBody activatePostRequestBody = new com.microsoft.graph.identitygovernance.lifecycleworkflows.workflows.item.microsoftgraphidentitygovernanceactivate.ActivatePostRequestBody();
LinkedList<User> subjects = new LinkedList<User>();
User user = new User();
user.setId("df744d9e-2148-4922-88a8-633896c1e929");
subjects.add(user);
activatePostRequestBody.setSubjects(subjects);
graphClient.identityGovernance().lifecycleWorkflows().workflows().byWorkflowId("{workflow-id}").microsoftGraphIdentityGovernanceActivate().post(activatePostRequestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const activate = {
    subjects: [\
        {\
            id: 'df744d9e-2148-4922-88a8-633896c1e929'\
        }\
    ]
};

await client.api('/identityGovernance/LifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833/activate')
	.post(activate);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\IdentityGovernance\LifecycleWorkflows\Workflows\Item\MicrosoftGraphIdentityGovernanceActivate\ActivatePostRequestBody;
use Microsoft\Graph\Generated\Models\User;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ActivatePostRequestBody();
$subjectsUser1 = new User();
$subjectsUser1->setId('df744d9e-2148-4922-88a8-633896c1e929');
$subjectsArray []= $subjectsUser1;
$requestBody->setSubjects($subjectsArray);

$graphServiceClient->identityGovernance()->lifecycleWorkflows()->workflows()->byWorkflowId('workflow-id')->microsoftGraphIdentityGovernanceActivate()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

$params = @{
	subjects = @(
		@{
			id = "df744d9e-2148-4922-88a8-633896c1e929"
		}
	)
}

Initialize-MgIdentityGovernanceLifecycleWorkflow -WorkflowId $workflowId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.identitygovernance.lifecycleworkflows.workflows.item.microsoft_graph_identity_governance_activate.activate_post_request_body import ActivatePostRequestBody
from msgraph.generated.models.user import User
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ActivatePostRequestBody(
	subjects = [\
		User(\
			id = "df744d9e-2148-4922-88a8-633896c1e929",\
		),\
	],
)

await graph_client.identity_governance.lifecycle_workflows.workflows.by_workflow_id('workflow-id').microsoft_graph_identity_governance_activate.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

## Check tasks and workflow status

You can monitor the status of the workflows and tasks at three levels.

- Monitor tasks at the user level.
- Monitor the aggregate high-level summary of the user-level results for a workflow within a specified period.
- Retrieve the detailed log of all tasks that were executed for a specific user in the workflow.

### Option 1: Monitor tasks for a workflow at the user level

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_3_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_3_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_3_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_3_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_3_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_3_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_3_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_3_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/identityGovernance/LifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833/userProcessingResults
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.IdentityGovernance.LifecycleWorkflows.Workflows["{workflow-id}"].UserProcessingResults.GetAsync();
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
userProcessingResults, err := graphClient.IdentityGovernance().LifecycleWorkflows().Workflows().ByWorkflowId("workflow-id").UserProcessingResults().Get(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.identitygovernance.UserProcessingResultCollectionResponse result = graphClient.identityGovernance().lifecycleWorkflows().workflows().byWorkflowId("{workflow-id}").userProcessingResults().get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let userProcessingResults = await client.api('/identityGovernance/LifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833/userProcessingResults')
	.get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->identityGovernance()->lifecycleWorkflows()->workflows()->byWorkflowId('workflow-id')->userProcessingResults()->get()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

Get-MgIdentityGovernanceLifecycleWorkflowUserProcessingResult -WorkflowId $workflowId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.identity_governance.lifecycle_workflows.workflows.by_workflow_id('workflow-id').user_processing_results.get()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identityGovernance/lifecycleWorkflows/workflows('15239232-66ed-445b-8292-2f5bbb2eb833')/userProcessingResults",
    "value": [\
        {\
            "id": "40efc576-840f-47d0-ab95-5abca800f8a2",\
            "completedDateTime": "2024-03-03T18:31:00.3581066Z",\
            "failedTasksCount": 0,\
            "processingStatus": "completed",\
            "scheduledDateTime": "2024-03-03T18:30:43.154495Z",\
            "startedDateTime": "2024-03-03T18:30:46.9357178Z",\
            "totalTasksCount": 3,\
            "totalUnprocessedTasksCount": 0,\
            "workflowExecutionType": "onDemand",\
            "workflowVersion": 1,\
            "subject": {\
                "id": "df744d9e-2148-4922-88a8-633896c1e929"\
            }\
        }\
    ]
}
```

### Option 2: Get the aggregate high-level summary of the user-level results for a workflow, within a specified period

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_4_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_4_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_4_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_4_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_4_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_4_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_4_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_4_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/identityGovernance/LifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833/userProcessingResults/summary(startDateTime=2024-03-01T00:00:00Z,endDateTime=2024-03-30T00:00:00Z)
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.IdentityGovernance.LifecycleWorkflows.Workflows["{workflow-id}"].UserProcessingResults.MicrosoftGraphIdentityGovernanceSummaryWithStartDateTimeWithEndDateTime(DateTimeOffset.Parse("{endDateTime}"),DateTimeOffset.Parse("{startDateTime}")).GetAsync();
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
startDateTime , err := time.Parse(time.RFC3339, "{startDateTime}")
endDateTime , err := time.Parse(time.RFC3339, "{endDateTime}")
microsoftGraphIdentityGovernanceSummary, err := graphClient.IdentityGovernance().LifecycleWorkflows().Workflows().ByWorkflowId("workflow-id").UserProcessingResults().MicrosoftGraphIdentityGovernanceSummaryWithStartDateTimeWithEndDateTime(&startDateTime, &endDateTime).Get(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

var result = graphClient.identityGovernance().lifecycleWorkflows().workflows().byWorkflowId("{workflow-id}").userProcessingResults().microsoftGraphIdentityGovernanceSummaryWithStartDateTimeWithEndDateTime(OffsetDateTime.parse("{endDateTime}"), OffsetDateTime.parse("{startDateTime}")).get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let userSummary = await client.api('/identityGovernance/LifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833/userProcessingResults/summary(startDateTime=2024-03-01T00:00:00Z,endDateTime=2024-03-30T00:00:00Z)')
	.get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->identityGovernance()->lifecycleWorkflows()->workflows()->byWorkflowId('workflow-id')->userProcessingResults()->microsoftGraphIdentityGovernanceSummaryWithStartDateTimeWithEndDateTime(new \DateTime('{endDateTime}'),new \DateTime('{startDateTime}'))->get()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

Invoke-MgSummaryIdentityGovernanceLifecycleWorkflowUserProcessingResult -WorkflowId $workflowId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.identity_governance.lifecycle_workflows.workflows.by_workflow_id('workflow-id').user_processing_results.microsoft_graph_identity_governance_summary_with_start_date_time_with_end_date_time("{endDateTime}","{startDateTime}").get()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#microsoft.graph.identityGovernance.userSummary",
    "failedTasks": 0,
    "failedUsers": 0,
    "successfulUsers": 1,
    "totalTasks": 3,
    "totalUsers": 1
}
```

### Option 3: Retrieve the detailed log of all tasks that were executed for a specific user in the workflow

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_5_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_5_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_5_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_5_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_5_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_5_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_5_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_5_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/identityGovernance/LifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833/userProcessingResults/40efc576-840f-47d0-ab95-5abca800f8a2/taskProcessingResults
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.IdentityGovernance.LifecycleWorkflows.Workflows["{workflow-id}"].UserProcessingResults["{userProcessingResult-id}"].TaskProcessingResults.GetAsync();
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
taskProcessingResults, err := graphClient.IdentityGovernance().LifecycleWorkflows().Workflows().ByWorkflowId("workflow-id").UserProcessingResults().ByUserProcessingResultId("userProcessingResult-id").TaskProcessingResults().Get(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.identitygovernance.TaskProcessingResultCollectionResponse result = graphClient.identityGovernance().lifecycleWorkflows().workflows().byWorkflowId("{workflow-id}").userProcessingResults().byUserProcessingResultId("{userProcessingResult-id}").taskProcessingResults().get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let taskProcessingResults = await client.api('/identityGovernance/LifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833/userProcessingResults/40efc576-840f-47d0-ab95-5abca800f8a2/taskProcessingResults')
	.get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->identityGovernance()->lifecycleWorkflows()->workflows()->byWorkflowId('workflow-id')->userProcessingResults()->byUserProcessingResultId('userProcessingResult-id')->taskProcessingResults()->get()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

Get-MgIdentityGovernanceLifecycleWorkflowUserProcessingResultTaskProcessingResult -WorkflowId $workflowId -UserProcessingResultId $userProcessingResultId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.identity_governance.lifecycle_workflows.workflows.by_workflow_id('workflow-id').user_processing_results.by_user_processing_result_id('userProcessingResult-id').task_processing_results.get()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identityGovernance/lifecycleWorkflows/workflows('15239232-66ed-445b-8292-2f5bbb2eb833')/userProcessingResults('40efc576-840f-47d0-ab95-5abca800f8a2')/taskProcessingResults",
    "value": [\
        {\
            "completedDateTime": "2024-03-03T18:30:50.483365Z",\
            "createdDateTime": "2024-03-03T18:30:47.6125438Z",\
            "id": "78650318-7238-4e7e-852f-2c36cbeff340",\
            "processingStatus": "completed",\
            "startedDateTime": "2024-03-03T18:30:50.0549446Z",\
            "failureReason": null,\
            "subject": {\
                "id": "df744d9e-2148-4922-88a8-633896c1e929"\
            },\
            "task": {\
                "category": "leaver",\
                "continueOnError": false,\
                "description": "Remove all licenses assigned to the user",\
                "displayName": "Remove all licenses for user",\
                "executionSequence": 1,\
                "id": "f71246b2-269c-4ba6-ab8e-afc1a05114cb",\
                "isEnabled": true,\
                "taskDefinitionId": "8fa97d28-3e52-4985-b3a9-a1126f9b8b4e",\
                "arguments": []\
            }\
        },\
        {\
            "completedDateTime": "2024-03-03T18:30:57.6034021Z",\
            "createdDateTime": "2024-03-03T18:30:47.8824313Z",\
            "id": "3d2e459d-5614-42e4-952b-0e917b5f6646",\
            "processingStatus": "completed",\
            "startedDateTime": "2024-03-03T18:30:53.6770279Z",\
            "failureReason": null,\
            "subject": {\
                "id": "df744d9e-2148-4922-88a8-633896c1e929"\
            },\
            "task": {\
                "category": "leaver",\
                "continueOnError": false,\
                "description": "Remove user from all Teams memberships",\
                "displayName": "Remove user from all Teams",\
                "executionSequence": 2,\
                "id": "ed545f03-e8d8-45fb-9cbd-15c937f2a866",\
                "isEnabled": true,\
                "taskDefinitionId": "81f7b200-2816-4b3b-8c5d-dc556f07b024",\
                "arguments": []\
            }\
        },\
        {\
            "completedDateTime": "2024-03-03T18:31:00.0894515Z",\
            "createdDateTime": "2024-03-03T18:30:48.0004721Z",\
            "id": "03359fa6-c63c-4573-92c2-4c9518ca98aa",\
            "processingStatus": "completed",\
            "startedDateTime": "2024-03-03T18:30:59.6195169Z",\
            "failureReason": null,\
            "subject": {\
                "id": "df744d9e-2148-4922-88a8-633896c1e929"\
            },\
            "task": {\
                "category": "leaver",\
                "continueOnError": false,\
                "description": "Delete user account in Azure AD",\
                "displayName": "Delete User Account",\
                "executionSequence": 3,\
                "id": "b4cefaa0-6ceb-461d-bbf5-ec69246463fd",\
                "isEnabled": true,\
                "taskDefinitionId": "8d18588d-9ad3-4c0f-99d0-ec215f0e3dff",\
                "arguments": []\
            }\
        }\
    ]
}
```

[Section titled: [Optional] Schedule the workflow to run automatically](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#optional-schedule-the-workflow-to-run-automatically)

## \[Optional\] Schedule the workflow to run automatically

After running your workflow on-demand and checking that everything works fine, you might want to enable the workflow to run automatically on a tenant-defined schedule. Run this request.

The request returns a `204 No Content` response code. When a workflow is scheduled, the Lifecycle Workflows engine checks every three hours for users in the associated execution condition and executes the configured tasks for those users. You can customize this recurrence from one hour to 24 hours.

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_6_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_6_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_6_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_6_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_6_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_6_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_6_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-lifecycle-workflows-scheduled-leaver?tabs=http#tabpanel_6_python)

HTTP

Copy

```http
PATCH https://graph.microsoft.com/v1.0/identityGovernance/lifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833
Content-type: application/json

{
    "isEnabled": true,
    "isSchedulingEnabled": true
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models.IdentityGovernance;

var requestBody = new Workflow
{
	IsEnabled = true,
	IsSchedulingEnabled = true,
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.IdentityGovernance.LifecycleWorkflows.Workflows["{workflow-id}"].PatchAsync(requestBody);
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
	  graphmodelsidentitygovernance "github.com/microsoftgraph/msgraph-sdk-go/models/identitygovernance"
	  //other-imports
)

requestBody := graphmodelsidentitygovernance.NewWorkflow()
isEnabled := true
requestBody.SetIsEnabled(&isEnabled)
isSchedulingEnabled := true
requestBody.SetIsSchedulingEnabled(&isSchedulingEnabled)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
workflows, err := graphClient.IdentityGovernance().LifecycleWorkflows().Workflows().ByWorkflowId("workflow-id").Patch(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.identitygovernance.Workflow workflow = new com.microsoft.graph.models.identitygovernance.Workflow();
workflow.setIsEnabled(true);
workflow.setIsSchedulingEnabled(true);
com.microsoft.graph.models.identitygovernance.Workflow result = graphClient.identityGovernance().lifecycleWorkflows().workflows().byWorkflowId("{workflow-id}").patch(workflow);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const workflow = {
    isEnabled: true,
    isSchedulingEnabled: true
};

await client.api('/identityGovernance/lifecycleWorkflows/workflows/15239232-66ed-445b-8292-2f5bbb2eb833')
	.update(workflow);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\IdentityGovernance\Workflow;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new Workflow();
$requestBody->setIsEnabled(true);
$requestBody->setIsSchedulingEnabled(true);

$result = $graphServiceClient->identityGovernance()->lifecycleWorkflows()->workflows()->byWorkflowId('workflow-id')->patch($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.Governance

$params = @{
	isEnabled = $true
	isSchedulingEnabled = $true
}

Update-MgIdentityGovernanceLifecycleWorkflow -WorkflowId $workflowId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.identity_governance.workflow import Workflow
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = Workflow(
	is_enabled = True,
	is_scheduling_enabled = True,
)

result = await graph_client.identity_governance.lifecycle_workflows.workflows.by_workflow_id('workflow-id').patch(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

## Related content

- [Automate employee offboarding tasks after their last day of work with the Microsoft Entra admin center](https://learn.microsoft.com/en-us/entra/id-governance/tutorial-scheduled-leaver-portal)
- [Overview of Microsoft Entra Lifecycle Workflows](https://learn.microsoft.com/en-us/graph/api/resources/identitygovernance-lifecycleworkflows-overview)
- [Overview of reporting in Microsoft Entra Lifecycle Workflows](https://learn.microsoft.com/en-us/graph/api/resources/identitygovernance-lifecycleworkflows-reporting-overview)

* * *
