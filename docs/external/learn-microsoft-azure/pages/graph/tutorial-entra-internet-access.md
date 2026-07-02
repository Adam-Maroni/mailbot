# Configure Microsoft Entra Internet Access using Microsoft Graph APIs

[Microsoft Entra Internet Access](https://learn.microsoft.com/en-us/entra/global-secure-access/concept-internet-access) provides an identity-centric Secure Web Gateway (SWG) solution for Software as a Service (SaaS) applications and other internet traffic. Admins use Microsoft Entra Internet Access to protect users, devices, and data from the Internet's wide threat landscape with best-in-class security controls and visibility through traffic logs. Deeply integrated with Microsoft Entra ID Conditional Access, Microsoft's SWG is identity-centric, making it easy for IT admins to manage their organization's policy in one engine.

In this tutorial, you learn how to configure Microsoft Entra Internet Access programmatically using the Microsoft Graph network access APIs. You:

- Create web content filtering policies to allow or block access to given destinations.
- Align web content filtering policies to Conditional Access policies via a filtering profile container, also known as a security profile.

Important

Some API operations in this tutorial use the `beta` endpoint.

## Prerequisites

To complete this tutorial, you need:

- A Microsoft Entra tenant with the Microsoft Entra Suite license.
- An API client such as [Graph Explorer](https://aka.ms/ge) with an account that has the supported administrator roles. The following Microsoft Entra roles are the least privileged for the operations in this tutorial:

  - Global Secure Access Administrator for configuring the Web content filtering policies and filtering profiles.
  - Conditional Access Administrator for configuring Conditional Access policies.
- Delegated permissions: _NetworkAccess.Read.All_, _NetworkAccess.ReadWrite.All_, and _Policy.ReadWrite.ConditionalAccess_
- A test user to assign to the Conditional Access policy.
- The [Global Secure Access (GSA) client](https://learn.microsoft.com/en-us/entra/global-secure-access/concept-clients) deployed to your organization's devices.

## Step 1: Enable Internet Access traffic forwarding

Before you configure Microsoft Entra Internet Access filtering policies, start by deploying the Global Secure Access (GSA) client to your organization's devices. Then begin forwarding traffic to GSA edge locations by enabling the Internet Access forwarding profile.

### Step 1.1: Retrieve the Internet Access traffic forwarding profile

Record the ID of the profile for use later in this tutorial.

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/beta/networkAccess/forwardingProfiles?$filter=trafficForwardingType eq 'internet'
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.NetworkAccess.ForwardingProfiles.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Filter = "trafficForwardingType eq 'internet'";
});
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
	  graphnetworkaccess "github.com/microsoftgraph/msgraph-beta-sdk-go/networkaccess"
	  //other-imports
)

requestFilter := "trafficForwardingType eq 'internet'"

requestParameters := &graphnetworkaccess.NetworkAccessForwardingProfilesRequestBuilderGetQueryParameters{
	Filter: &requestFilter,
}
configuration := &graphnetworkaccess.NetworkAccessForwardingProfilesRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
forwardingProfiles, err := graphClient.NetworkAccess().ForwardingProfiles().Get(context.Background(), configuration)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.networkaccess.ForwardingProfileCollectionResponse result = graphClient.networkAccess().forwardingProfiles().get(requestConfiguration -> {
	requestConfiguration.queryParameters.filter = "trafficForwardingType eq 'internet'";
});
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let forwardingProfiles = await client.api('/networkAccess/forwardingProfiles')
	.version('beta')
	.filter('trafficForwardingType eq \'internet\'')
	.get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\Beta\GraphServiceClient;
use Microsoft\Graph\Beta\Generated\NetworkAccess\ForwardingProfiles\ForwardingProfilesRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new ForwardingProfilesRequestBuilderGetRequestConfiguration();
$queryParameters = ForwardingProfilesRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->filter = "trafficForwardingType eq 'internet'";
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->networkAccess()->forwardingProfiles()->get($requestConfiguration)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Beta.NetworkAccess

Get-MgBetaNetworkAccessForwardingProfile -Filter "trafficForwardingType eq 'internet'"
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph_beta import GraphServiceClient
from msgraph_beta.generated.network_access.forwarding_profiles.forwarding_profiles_request_builder import ForwardingProfilesRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = ForwardingProfilesRequestBuilder.ForwardingProfilesRequestBuilderGetQueryParameters(
		filter = "trafficForwardingType eq 'internet'",
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.network_access.forwarding_profiles.get(request_configuration = request_configuration)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "trafficForwardingType": "internet",
  "priority": 2,
  "id": "bbbbbbbb-1111-2222-3333-cccccccccccc",
  "name": "Internet traffic forwarding profile",
  "description": "Default traffic forwarding profile for Internet traffic acquisition. Assign the profile to client or branch offices to acquire Internet traffic for Zero Trust Network Access.Internet traffic forwarding profile will exclude all endpoints defined in Microsoft 365 traffic forwarding profile.",
  "state": "enabled",
  "version": "1.0.0",
  "lastModifiedDateTime": "2025-01-14T13:11:57.9295327Z",
  "associations": [],
  "servicePrincipal": {
    "appId": "00001111-aaaa-2222-bbbb-3333cccc4444",
    "id": "aaaaaaaa-0000-1111-2222-bbbbbbbbbbbb"
  }
}
```

### Step 1.2: Enable the state of Internet Access forwarding profile

The request returns a `204 No Content` response.

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_2_python)

HTTP

Copy

```http
PATCH https://graph.microsoft.com/beta/networkAccess/forwardingProfiles/bbbbbbbb-1111-2222-3333-cccccccccccc
Content-type: application/json

{
  "state": "enabled"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Beta.Models.Networkaccess;

var requestBody = new ForwardingProfile
{
	State = Status.Enabled,
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.NetworkAccess.ForwardingProfiles["{forwardingProfile-id}"].PatchAsync(requestBody);
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
	  graphmodelsnetworkaccess "github.com/microsoftgraph/msgraph-beta-sdk-go/models/networkaccess"
	  //other-imports
)

requestBody := graphmodelsnetworkaccess.NewForwardingProfile()
state := graphmodels.ENABLED_STATUS
requestBody.SetState(&state)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
forwardingProfiles, err := graphClient.NetworkAccess().ForwardingProfiles().ByForwardingProfileId("forwardingProfile-id").Patch(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.beta.models.networkaccess.ForwardingProfile forwardingProfile = new com.microsoft.graph.beta.models.networkaccess.ForwardingProfile();
forwardingProfile.setState(com.microsoft.graph.beta.models.networkaccess.Status.Enabled);
com.microsoft.graph.models.networkaccess.ForwardingProfile result = graphClient.networkAccess().forwardingProfiles().byForwardingProfileId("{forwardingProfile-id}").patch(forwardingProfile);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const forwardingProfile = {
  state: 'enabled'
};

await client.api('/networkAccess/forwardingProfiles/bbbbbbbb-1111-2222-3333-cccccccccccc')
	.version('beta')
	.update(forwardingProfile);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\Beta\GraphServiceClient;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\ForwardingProfile;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\Status;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ForwardingProfile();
$requestBody->setState(new Status('enabled'));

$result = $graphServiceClient->networkAccess()->forwardingProfiles()->byForwardingProfileId('forwardingProfile-id')->patch($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Beta.NetworkAccess

$params = @{
	state = "enabled"
}

Update-MgBetaNetworkAccessForwardingProfile -ForwardingProfileId $forwardingProfileId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph_beta import GraphServiceClient
from msgraph_beta.generated.models.networkaccess.forwarding_profile import ForwardingProfile
from msgraph_beta.generated.models.status import Status
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ForwardingProfile(
	state = Status.Enabled,
)

result = await graph_client.network_access.forwarding_profiles.by_forwarding_profile_id('forwardingProfile-id').patch(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

## Step 2: Create a web content filtering policy and security profile

To configure policies in Microsoft Entra Internet Access, you first need to create a filtering policy, which is a collection of rules governing access to destinations like web categories and Fully Qualified Domain Names (FQDNs). For example, you can create a filtering policy with rules that block access to the Artificial Intelligence category and individual FQDNs. Then you organize filtering policies into a security profile that you can target with Conditional Access policies.

### Step 2.1: Create a web content filtering policy

In this example, you create a filtering policy with rules that block access to the "Artificial Intelligence" category and FQDNs for `bing.com`. Once this policy is created, take note of the filtering policy ID for linking in the filtering profile.

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_3_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_3_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_3_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_3_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_3_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_3_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_3_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_3_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/beta/networkaccess/filteringPolicies
Content-type: application/json

{
  "name": "AI and Bing",
  "policyRules": [\
    {\
      "@odata.type": "#microsoft.graph.networkaccess.webCategoryFilteringRule",\
      "name": "AI",\
      "ruleType": "webCategory",\
      "destinations": [\
        {\
          "@odata.type": "#microsoft.graph.networkaccess.webCategory",\
          "name": "ArtificialIntelligence"\
        }\
      ]\
    },\
    {\
      "@odata.type": "#microsoft.graph.networkaccess.fqdnFilteringRule",\
      "name": "bing FQDNs",\
      "ruleType": "fqdn",\
      "destinations": [\
        {\
          "@odata.type": "#microsoft.graph.networkaccess.fqdn",\
          "value": "bing.com"\
        },\
        {\
          "@odata.type": "#microsoft.graph.networkaccess.fqdn",\
          "value": "*.bing.com"\
        }\
      ]\
    }\
  ],
  "action": "block"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Beta.Models.Networkaccess;

var requestBody = new FilteringPolicy
{
	Name = "AI and Bing",
	PolicyRules = new List<PolicyRule>
	{
		new WebCategoryFilteringRule
		{
			OdataType = "#microsoft.graph.networkaccess.webCategoryFilteringRule",
			Name = "AI",
			RuleType = NetworkDestinationType.WebCategory,
			Destinations = new List<RuleDestination>
			{
				new WebCategory
				{
					OdataType = "#microsoft.graph.networkaccess.webCategory",
					Name = "ArtificialIntelligence",
				},
			},
		},
		new FqdnFilteringRule
		{
			OdataType = "#microsoft.graph.networkaccess.fqdnFilteringRule",
			Name = "bing FQDNs",
			RuleType = NetworkDestinationType.Fqdn,
			Destinations = new List<RuleDestination>
			{
				new Fqdn
				{
					OdataType = "#microsoft.graph.networkaccess.fqdn",
					Value = "bing.com",
				},
				new Fqdn
				{
					OdataType = "#microsoft.graph.networkaccess.fqdn",
					Value = "*.bing.com",
				},
			},
		},
	},
	Action = FilteringPolicyAction.Block,
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.NetworkAccess.FilteringPolicies.PostAsync(requestBody);
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
	  graphmodelsnetworkaccess "github.com/microsoftgraph/msgraph-beta-sdk-go/models/networkaccess"
	  //other-imports
)

requestBody := graphmodelsnetworkaccess.NewFilteringPolicy()
name := "AI and Bing"
requestBody.SetName(&name)

policyRule := graphmodelsnetworkaccess.NewWebCategoryFilteringRule()
name := "AI"
policyRule.SetName(&name)
ruleType := graphmodels.WEBCATEGORY_NETWORKDESTINATIONTYPE
policyRule.SetRuleType(&ruleType)

ruleDestination := graphmodelsnetworkaccess.NewWebCategory()
name := "ArtificialIntelligence"
ruleDestination.SetName(&name)

destinations := []graphmodelsnetworkaccess.RuleDestinationable {
	ruleDestination,
}
policyRule.SetDestinations(destinations)
policyRule1 := graphmodelsnetworkaccess.NewFqdnFilteringRule()
name := "bing FQDNs"
policyRule1.SetName(&name)
ruleType := graphmodels.FQDN_NETWORKDESTINATIONTYPE
policyRule1.SetRuleType(&ruleType)

ruleDestination := graphmodelsnetworkaccess.NewFqdn()
value := "bing.com"
ruleDestination.SetValue(&value)
ruleDestination1 := graphmodelsnetworkaccess.NewFqdn()
value := "*.bing.com"
ruleDestination1.SetValue(&value)

destinations := []graphmodelsnetworkaccess.RuleDestinationable {
	ruleDestination,
	ruleDestination1,
}
policyRule1.SetDestinations(destinations)

policyRules := []graphmodelsnetworkaccess.PolicyRuleable {
	policyRule,
	policyRule1,
}
requestBody.SetPolicyRules(policyRules)
action := graphmodels.BLOCK_FILTERINGPOLICYACTION
requestBody.SetAction(&action)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
filteringPolicies, err := graphClient.NetworkAccess().FilteringPolicies().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.beta.models.networkaccess.FilteringPolicy filteringPolicy = new com.microsoft.graph.beta.models.networkaccess.FilteringPolicy();
filteringPolicy.setName("AI and Bing");
LinkedList<com.microsoft.graph.beta.models.networkaccess.PolicyRule> policyRules = new LinkedList<com.microsoft.graph.beta.models.networkaccess.PolicyRule>();
com.microsoft.graph.beta.models.networkaccess.WebCategoryFilteringRule policyRule = new com.microsoft.graph.beta.models.networkaccess.WebCategoryFilteringRule();
policyRule.setOdataType("#microsoft.graph.networkaccess.webCategoryFilteringRule");
policyRule.setName("AI");
policyRule.setRuleType(com.microsoft.graph.beta.models.networkaccess.NetworkDestinationType.WebCategory);
LinkedList<com.microsoft.graph.beta.models.networkaccess.RuleDestination> destinations = new LinkedList<com.microsoft.graph.beta.models.networkaccess.RuleDestination>();
com.microsoft.graph.beta.models.networkaccess.WebCategory ruleDestination = new com.microsoft.graph.beta.models.networkaccess.WebCategory();
ruleDestination.setOdataType("#microsoft.graph.networkaccess.webCategory");
ruleDestination.setName("ArtificialIntelligence");
destinations.add(ruleDestination);
policyRule.setDestinations(destinations);
policyRules.add(policyRule);
com.microsoft.graph.beta.models.networkaccess.FqdnFilteringRule policyRule1 = new com.microsoft.graph.beta.models.networkaccess.FqdnFilteringRule();
policyRule1.setOdataType("#microsoft.graph.networkaccess.fqdnFilteringRule");
policyRule1.setName("bing FQDNs");
policyRule1.setRuleType(com.microsoft.graph.beta.models.networkaccess.NetworkDestinationType.Fqdn);
LinkedList<com.microsoft.graph.beta.models.networkaccess.RuleDestination> destinations1 = new LinkedList<com.microsoft.graph.beta.models.networkaccess.RuleDestination>();
com.microsoft.graph.beta.models.networkaccess.Fqdn ruleDestination1 = new com.microsoft.graph.beta.models.networkaccess.Fqdn();
ruleDestination1.setOdataType("#microsoft.graph.networkaccess.fqdn");
ruleDestination1.setValue("bing.com");
destinations1.add(ruleDestination1);
com.microsoft.graph.beta.models.networkaccess.Fqdn ruleDestination2 = new com.microsoft.graph.beta.models.networkaccess.Fqdn();
ruleDestination2.setOdataType("#microsoft.graph.networkaccess.fqdn");
ruleDestination2.setValue("*.bing.com");
destinations1.add(ruleDestination2);
policyRule1.setDestinations(destinations1);
policyRules.add(policyRule1);
filteringPolicy.setPolicyRules(policyRules);
filteringPolicy.setAction(com.microsoft.graph.beta.models.networkaccess.FilteringPolicyAction.Block);
com.microsoft.graph.models.networkaccess.FilteringPolicy result = graphClient.networkAccess().filteringPolicies().post(filteringPolicy);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const filteringPolicy = {
  name: 'AI and Bing',
  policyRules: [\
    {\
      '@odata.type': '#microsoft.graph.networkaccess.webCategoryFilteringRule',\
      name: 'AI',\
      ruleType: 'webCategory',\
      destinations: [\
        {\
          '@odata.type': '#microsoft.graph.networkaccess.webCategory',\
          name: 'ArtificialIntelligence'\
        }\
      ]\
    },\
    {\
      '@odata.type': '#microsoft.graph.networkaccess.fqdnFilteringRule',\
      name: 'bing FQDNs',\
      ruleType: 'fqdn',\
      destinations: [\
        {\
          '@odata.type': '#microsoft.graph.networkaccess.fqdn',\
          value: 'bing.com'\
        },\
        {\
          '@odata.type': '#microsoft.graph.networkaccess.fqdn',\
          value: '*.bing.com'\
        }\
      ]\
    }\
  ],
  action: 'block'
};

await client.api('/networkaccess/filteringPolicies')
	.version('beta')
	.post(filteringPolicy);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\Beta\GraphServiceClient;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\FilteringPolicy;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\PolicyRule;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\WebCategoryFilteringRule;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\NetworkDestinationType;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\RuleDestination;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\WebCategory;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\FqdnFilteringRule;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\Fqdn;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\FilteringPolicyAction;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new FilteringPolicy();
$requestBody->setName('AI and Bing');
$policyRulesPolicyRule1 = new WebCategoryFilteringRule();
$policyRulesPolicyRule1->setOdataType('#microsoft.graph.networkaccess.webCategoryFilteringRule');
$policyRulesPolicyRule1->setName('AI');
$policyRulesPolicyRule1->setRuleType(new NetworkDestinationType('webCategory'));
$destinationsRuleDestination1 = new WebCategory();
$destinationsRuleDestination1->setOdataType('#microsoft.graph.networkaccess.webCategory');
$destinationsRuleDestination1->setName('ArtificialIntelligence');
$destinationsArray []= $destinationsRuleDestination1;
$policyRulesPolicyRule1->setDestinations($destinationsArray);

$policyRulesArray []= $policyRulesPolicyRule1;
$policyRulesPolicyRule2 = new FqdnFilteringRule();
$policyRulesPolicyRule2->setOdataType('#microsoft.graph.networkaccess.fqdnFilteringRule');
$policyRulesPolicyRule2->setName('bing FQDNs');
$policyRulesPolicyRule2->setRuleType(new NetworkDestinationType('fqdn'));
$destinationsRuleDestination1 = new Fqdn();
$destinationsRuleDestination1->setOdataType('#microsoft.graph.networkaccess.fqdn');
$destinationsRuleDestination1->setValue('bing.com');
$destinationsArray []= $destinationsRuleDestination1;
$destinationsRuleDestination2 = new Fqdn();
$destinationsRuleDestination2->setOdataType('#microsoft.graph.networkaccess.fqdn');
$destinationsRuleDestination2->setValue('*.bing.com');
$destinationsArray []= $destinationsRuleDestination2;
$policyRulesPolicyRule2->setDestinations($destinationsArray);

$policyRulesArray []= $policyRulesPolicyRule2;
$requestBody->setPolicyRules($policyRulesArray);

$requestBody->setAction(new FilteringPolicyAction('block'));

$result = $graphServiceClient->networkAccess()->filteringPolicies()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Beta.NetworkAccess

$params = @{
	name = "AI and Bing"
	policyRules = @(
		@{
			"@odata.type" = "#microsoft.graph.networkaccess.webCategoryFilteringRule"
			name = "AI"
			ruleType = "webCategory"
			destinations = @(
				@{
					"@odata.type" = "#microsoft.graph.networkaccess.webCategory"
					name = "ArtificialIntelligence"
				}
			)
		}
		@{
			"@odata.type" = "#microsoft.graph.networkaccess.fqdnFilteringRule"
			name = "bing FQDNs"
			ruleType = "fqdn"
			destinations = @(
				@{
					"@odata.type" = "#microsoft.graph.networkaccess.fqdn"
					value = "bing.com"
				}
				@{
					"@odata.type" = "#microsoft.graph.networkaccess.fqdn"
					value = "*.bing.com"
				}
			)
		}
	)
	action = "block"
}

New-MgBetaNetworkAccessFilteringPolicy -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph_beta import GraphServiceClient
from msgraph_beta.generated.models.networkaccess.filtering_policy import FilteringPolicy
from msgraph_beta.generated.models.networkaccess.policy_rule import PolicyRule
from msgraph_beta.generated.models.networkaccess.web_category_filtering_rule import WebCategoryFilteringRule
from msgraph_beta.generated.models.network_destination_type import NetworkDestinationType
from msgraph_beta.generated.models.networkaccess.rule_destination import RuleDestination
from msgraph_beta.generated.models.networkaccess.web_category import WebCategory
from msgraph_beta.generated.models.networkaccess.fqdn_filtering_rule import FqdnFilteringRule
from msgraph_beta.generated.models.networkaccess.fqdn import Fqdn
from msgraph_beta.generated.models.filtering_policy_action import FilteringPolicyAction
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = FilteringPolicy(
	name = "AI and Bing",
	policy_rules = [\
		WebCategoryFilteringRule(\
			odata_type = "#microsoft.graph.networkaccess.webCategoryFilteringRule",\
			name = "AI",\
			rule_type = NetworkDestinationType.WebCategory,\
			destinations = [\
				WebCategory(\
					odata_type = "#microsoft.graph.networkaccess.webCategory",\
					name = "ArtificialIntelligence",\
				),\
			],\
		),\
		FqdnFilteringRule(\
			odata_type = "#microsoft.graph.networkaccess.fqdnFilteringRule",\
			name = "bing FQDNs",\
			rule_type = NetworkDestinationType.Fqdn,\
			destinations = [\
				Fqdn(\
					odata_type = "#microsoft.graph.networkaccess.fqdn",\
					value = "bing.com",\
				),\
				Fqdn(\
					odata_type = "#microsoft.graph.networkaccess.fqdn",\
					value = "*.bing.com",\
				),\
			],\
		),\
	],
	action = FilteringPolicyAction.Block,
)

result = await graph_client.network_access.filtering_policies.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
  "id": "cccccccc-2222-3333-4444-dddddddddddd",
  "name": "AI and Bing",
  "description": null,
  "version": "1.0.0",
  "lastModifiedDateTime": "2025-02-05T18:10:28.9760687Z",
  "createdDateTime": "2025-02-05T18:10:27Z",
  "action": "block"
}
```

### Step 2.2: Edit or update the web content filtering policy

After creating a filtering policy, you can programmatically edit or update it. You can add new rules to the policy by sending a POST request or update destinations in existing rules using a PATCH request. Either of these changes allow you to adjust filtering policies as your organization's needs change, such as blocking more categories or domains, or modifying existing rules.

In this example, you use a PATCH request to add a destination to the rule created in step 2.1.

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_4_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_4_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_4_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_4_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_4_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_4_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_4_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_4_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/beta/networkaccess/filteringPolicies('cccccccc-2222-3333-4444-dddddddddddd')/policyRules('<policyRuleId>')
Content-type: application/json

{
  "@odata.type": "#microsoft.graph.networkaccess.fqdnFilteringRule",
  "destinations": [\
    {\
      "@odata.type": "#microsoft.graph.networkaccess.fqdn",\
      "value": "bing.com"\
    },\
    {\
      "@odata.type": "#microsoft.graph.networkaccess.fqdn",\
      "value": "*.bing.com"\
    },\
    {\
      "@odata.type": "#microsoft.graph.networkaccess.fqdn",\
      "value": "bing.co.uk"\
    }\
  ]
}
```

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const policyRule = {
  '@odata.type': '#microsoft.graph.networkaccess.fqdnFilteringRule',
  destinations: [\
    {\
      '@odata.type': '#microsoft.graph.networkaccess.fqdn',\
      value: 'bing.com'\
    },\
    {\
      '@odata.type': '#microsoft.graph.networkaccess.fqdn',\
      value: '*.bing.com'\
    },\
    {\
      '@odata.type': '#microsoft.graph.networkaccess.fqdn',\
      value: 'bing.co.uk'\
    }\
  ]
};

await client.api('/networkaccess/filteringPolicies('cccccccc-2222-3333-4444-dddddddddddd')/policyRules('<policyRuleId>')')
	.version('beta')
	.post(policyRule);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
  "@odata.type": "#microsoft.graph.networkaccess.fqdnFilteringRule",
  "id": "cccccccc-2222-3333-4444-dddddddddddd",
  "name": "bing FQDNs",
  "ruleType": "fqdn",
  "destinations": [\
    {\
        "@odata.type": "#microsoft.graph.networkaccess.fqdn",\
        "value": "google.co.uk"\
    },\
    {\
        "@odata.type": "#microsoft.graph.networkaccess.fqdn",\
        "value": "google.com"\
    },\
    {\
        "@odata.type": "#microsoft.graph.networkaccess.fqdn",\
        "value": "bing.com"\
    }\
  ]
}
```

### Step 2.3: Create a filtering profile or security profile

Create a filtering or security profile to hold your policies and target it in Conditional Access session control. After creating the profile, note the filtering profile ID for later use in the Conditional Access policy.

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_5_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_5_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_5_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_5_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_5_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_5_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_5_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_5_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/beta/networkaccess/filteringProfiles
Content-type: application/json

{
  "name": "Security Profile for UserA",
  "state": "enabled",
  "priority": 100,
  "policies": []
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Beta.Models.Networkaccess;

var requestBody = new FilteringProfile
{
	Name = "Security Profile for UserA",
	State = Status.Enabled,
	Priority = 100L,
	Policies = new List<PolicyLink>
	{
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.NetworkAccess.FilteringProfiles.PostAsync(requestBody);
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
	  graphmodelsnetworkaccess "github.com/microsoftgraph/msgraph-beta-sdk-go/models/networkaccess"
	  //other-imports
)

requestBody := graphmodelsnetworkaccess.NewFilteringProfile()
name := "Security Profile for UserA"
requestBody.SetName(&name)
state := graphmodels.ENABLED_STATUS
requestBody.SetState(&state)
priority := int64(100)
requestBody.SetPriority(&priority)
policies := []graphmodelsnetworkaccess.PolicyLinkable {

}
requestBody.SetPolicies(policies)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
filteringProfiles, err := graphClient.NetworkAccess().FilteringProfiles().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.beta.models.networkaccess.FilteringProfile filteringProfile = new com.microsoft.graph.beta.models.networkaccess.FilteringProfile();
filteringProfile.setName("Security Profile for UserA");
filteringProfile.setState(com.microsoft.graph.beta.models.networkaccess.Status.Enabled);
filteringProfile.setPriority(100L);
LinkedList<com.microsoft.graph.beta.models.networkaccess.PolicyLink> policies = new LinkedList<com.microsoft.graph.beta.models.networkaccess.PolicyLink>();
filteringProfile.setPolicies(policies);
com.microsoft.graph.models.networkaccess.FilteringProfile result = graphClient.networkAccess().filteringProfiles().post(filteringProfile);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const filteringProfile = {
  name: 'Security Profile for UserA',
  state: 'enabled',
  priority: 100,
  policies: []
};

await client.api('/networkaccess/filteringProfiles')
	.version('beta')
	.post(filteringProfile);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\Beta\GraphServiceClient;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\FilteringProfile;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\Status;
use Microsoft\Graph\Beta\Generated\Models\Networkaccess\PolicyLink;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new FilteringProfile();
$requestBody->setName('Security Profile for UserA');
$requestBody->setState(new Status('enabled'));
$requestBody->setPriority(100);
$requestBody->setPolicies([	]);

$result = $graphServiceClient->networkAccess()->filteringProfiles()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Beta.NetworkAccess

$params = @{
	name = "Security Profile for UserA"
	state = "enabled"
	priority = 100
	policies = @(
	)
}

New-MgBetaNetworkAccessFilteringProfile -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph_beta import GraphServiceClient
from msgraph_beta.generated.models.networkaccess.filtering_profile import FilteringProfile
from msgraph_beta.generated.models.status import Status
from msgraph_beta.generated.models.networkaccess.policy_link import PolicyLink
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = FilteringProfile(
	name = "Security Profile for UserA",
	state = Status.Enabled,
	priority = 100,
	policies = [\
	],
)

result = await graph_client.network_access.filtering_profiles.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
  "priority": 100,
  "createdDateTime": "2025-02-05T18:27:31Z",
  "id": "dddddddd-3333-4444-5555-eeeeeeeeeeee",
  "name": "Security Profile for UserA",
  "description": null,
  "state": "enabled",
  "version": "1.0.0",
  "lastModifiedDateTime": "2025-02-05T18:27:31.660891Z"
}
```

### Step 2.4: Link the filtering policy to the filtering profile or security profile

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_6_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_6_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_6_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_6_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_6_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_6_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_6_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_6_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/beta/networkaccess/filteringProfiles/dddddddd-3333-4444-5555-eeeeeeeeeeee/policies
Content-type: application/json

{
  "priority": 100,
    "state": "enabled",
    "@odata.type": "#microsoft.graph.networkaccess.filteringPolicyLink",
    "loggingState": "enabled",
    "policy": {
        "id": "cccccccc-2222-3333-4444-dddddddddddd",
        "@odata.type": "#microsoft.graph.networkaccess.filteringPolicy"
}
```

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const policyLink = {
  priority: 100,
    state: 'enabled',
    '@odata.type': '#microsoft.graph.networkaccess.filteringPolicyLink',
    loggingState: 'enabled',
    policy: {
        id: 'cccccccc-2222-3333-4444-dddddddddddd',
        '@odata.type': '#microsoft.graph.networkaccess.filteringPolicy'
};

await client.api('/networkaccess/filteringProfiles/dddddddd-3333-4444-5555-eeeeeeeeeeee/policies')
	.version('beta')
	.post(policyLink);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Copy

```
Snippet not available
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
    "id": "dddddddd-9999-0000-1111-eeeeeeeeeeee",
    "priority": 100,
    "state": "enabled",
    "version": "1.0.0",
    "loggingState": "enabled",
    "lastModifiedDateTime": "2025-02-05T18:31:32Z",
    "createdDateTime": "2025-02-05T18:31:32Z",
    "policy": {
        "@odata.type": "#microsoft.graph.networkaccess.filteringPolicy",
        "id": "cccccccc-2222-3333-4444-dddddddddddd",
        "name": "AI and Bing",
        "description": null,
        "version": "1.0.0",
        "lastModifiedDateTime": "2025-02-05T18:15:17.0759384Z",
        "createdDateTime": "2025-02-05T18:15:16Z",
        "action": "block"
    }
}
```

## Step 3: Link a Conditional Access policy

To enforce your filtering profile, you need to link it to a Conditional Access (CA) policy. Doing so makes the contents of your filtering profile user- and context-aware. In this step, you create a CA policy with the following settings:

- Target it to a user with ID `00aa00aa-bb11-cc22-dd33-44ee44ee44ee` and the app "All internet resources with Global Secure Access" with **appId**`5dc48733-b5df-475c-a49b-fa307ef00853`.
- Configure a session control with **globalSecureAccessFilteringProfile** ID `dddddddd-9999-0000-1111-eeeeeeeeeeee`.

### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_7_http)
- [C#](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_7_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_7_go)
- [Java](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_7_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_7_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_7_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_7_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access?tabs=http#tabpanel_7_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/beta/identity/conditionalAccess/policies
Content-type: application/json

{
    "conditions": {
        "applications": {
            "includeApplications": [\
                "5dc48733-b5df-475c-a49b-fa307ef00853"\
            ]
        },
        "users": {
            "includeUsers": [\
                "00aa00aa-bb11-cc22-dd33-44ee44ee44ee"\
            ]
        }
    },
    "displayName": "UserA Access to AI and Bing",
    "sessionControls": {
        "globalSecureAccessFilteringProfile": {
            "profileId": "dddddddd-9999-0000-1111-eeeeeeeeeeee",
            "isEnabled": true
        }
    },
    "state": "enabled"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Beta.Models;

var requestBody = new ConditionalAccessPolicy
{
	Conditions = new ConditionalAccessConditionSet
	{
		Applications = new ConditionalAccessApplications
		{
			IncludeApplications = new List<string>
			{
				"5dc48733-b5df-475c-a49b-fa307ef00853",
			},
		},
		Users = new ConditionalAccessUsers
		{
			IncludeUsers = new List<string>
			{
				"00aa00aa-bb11-cc22-dd33-44ee44ee44ee",
			},
		},
	},
	DisplayName = "UserA Access to AI and Bing",
	SessionControls = new ConditionalAccessSessionControls
	{
		GlobalSecureAccessFilteringProfile = new GlobalSecureAccessFilteringProfileSessionControl
		{
			ProfileId = "dddddddd-9999-0000-1111-eeeeeeeeeeee",
			IsEnabled = true,
		},
	},
	State = ConditionalAccessPolicyState.Enabled,
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Identity.ConditionalAccess.Policies.PostAsync(requestBody);
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
	  graphmodels "github.com/microsoftgraph/msgraph-beta-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewConditionalAccessPolicy()
conditions := graphmodels.NewConditionalAccessConditionSet()
applications := graphmodels.NewConditionalAccessApplications()
includeApplications := []string {
	"5dc48733-b5df-475c-a49b-fa307ef00853",
}
applications.SetIncludeApplications(includeApplications)
conditions.SetApplications(applications)
users := graphmodels.NewConditionalAccessUsers()
includeUsers := []string {
	"00aa00aa-bb11-cc22-dd33-44ee44ee44ee",
}
users.SetIncludeUsers(includeUsers)
conditions.SetUsers(users)
requestBody.SetConditions(conditions)
displayName := "UserA Access to AI and Bing"
requestBody.SetDisplayName(&displayName)
sessionControls := graphmodels.NewConditionalAccessSessionControls()
globalSecureAccessFilteringProfile := graphmodels.NewGlobalSecureAccessFilteringProfileSessionControl()
profileId := "dddddddd-9999-0000-1111-eeeeeeeeeeee"
globalSecureAccessFilteringProfile.SetProfileId(&profileId)
isEnabled := true
globalSecureAccessFilteringProfile.SetIsEnabled(&isEnabled)
sessionControls.SetGlobalSecureAccessFilteringProfile(globalSecureAccessFilteringProfile)
requestBody.SetSessionControls(sessionControls)
state := graphmodels.ENABLED_CONDITIONALACCESSPOLICYSTATE
requestBody.SetState(&state)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
policies, err := graphClient.Identity().ConditionalAccess().Policies().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ConditionalAccessPolicy conditionalAccessPolicy = new ConditionalAccessPolicy();
ConditionalAccessConditionSet conditions = new ConditionalAccessConditionSet();
ConditionalAccessApplications applications = new ConditionalAccessApplications();
LinkedList<String> includeApplications = new LinkedList<String>();
includeApplications.add("5dc48733-b5df-475c-a49b-fa307ef00853");
applications.setIncludeApplications(includeApplications);
conditions.setApplications(applications);
ConditionalAccessUsers users = new ConditionalAccessUsers();
LinkedList<String> includeUsers = new LinkedList<String>();
includeUsers.add("00aa00aa-bb11-cc22-dd33-44ee44ee44ee");
users.setIncludeUsers(includeUsers);
conditions.setUsers(users);
conditionalAccessPolicy.setConditions(conditions);
conditionalAccessPolicy.setDisplayName("UserA Access to AI and Bing");
ConditionalAccessSessionControls sessionControls = new ConditionalAccessSessionControls();
GlobalSecureAccessFilteringProfileSessionControl globalSecureAccessFilteringProfile = new GlobalSecureAccessFilteringProfileSessionControl();
globalSecureAccessFilteringProfile.setProfileId("dddddddd-9999-0000-1111-eeeeeeeeeeee");
globalSecureAccessFilteringProfile.setIsEnabled(true);
sessionControls.setGlobalSecureAccessFilteringProfile(globalSecureAccessFilteringProfile);
conditionalAccessPolicy.setSessionControls(sessionControls);
conditionalAccessPolicy.setState(ConditionalAccessPolicyState.Enabled);
ConditionalAccessPolicy result = graphClient.identity().conditionalAccess().policies().post(conditionalAccessPolicy);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const conditionalAccessPolicy = {
    conditions: {
        applications: {
            includeApplications: [\
                '5dc48733-b5df-475c-a49b-fa307ef00853'\
            ]
        },
        users: {
            includeUsers: [\
                '00aa00aa-bb11-cc22-dd33-44ee44ee44ee'\
            ]
        }
    },
    displayName: 'UserA Access to AI and Bing',
    sessionControls: {
        globalSecureAccessFilteringProfile: {
            profileId: 'dddddddd-9999-0000-1111-eeeeeeeeeeee',
            isEnabled: true
        }
    },
    state: 'enabled'
};

await client.api('/identity/conditionalAccess/policies')
	.version('beta')
	.post(conditionalAccessPolicy);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\Beta\GraphServiceClient;
use Microsoft\Graph\Beta\Generated\Models\ConditionalAccessPolicy;
use Microsoft\Graph\Beta\Generated\Models\ConditionalAccessConditionSet;
use Microsoft\Graph\Beta\Generated\Models\ConditionalAccessApplications;
use Microsoft\Graph\Beta\Generated\Models\ConditionalAccessUsers;
use Microsoft\Graph\Beta\Generated\Models\ConditionalAccessSessionControls;
use Microsoft\Graph\Beta\Generated\Models\GlobalSecureAccessFilteringProfileSessionControl;
use Microsoft\Graph\Beta\Generated\Models\ConditionalAccessPolicyState;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ConditionalAccessPolicy();
$conditions = new ConditionalAccessConditionSet();
$conditionsApplications = new ConditionalAccessApplications();
$conditionsApplications->setIncludeApplications(['5dc48733-b5df-475c-a49b-fa307ef00853', 	]);
$conditions->setApplications($conditionsApplications);
$conditionsUsers = new ConditionalAccessUsers();
$conditionsUsers->setIncludeUsers(['00aa00aa-bb11-cc22-dd33-44ee44ee44ee', 	]);
$conditions->setUsers($conditionsUsers);
$requestBody->setConditions($conditions);
$requestBody->setDisplayName('UserA Access to AI and Bing');
$sessionControls = new ConditionalAccessSessionControls();
$sessionControlsGlobalSecureAccessFilteringProfile = new GlobalSecureAccessFilteringProfileSessionControl();
$sessionControlsGlobalSecureAccessFilteringProfile->setProfileId('dddddddd-9999-0000-1111-eeeeeeeeeeee');
$sessionControlsGlobalSecureAccessFilteringProfile->setIsEnabled(true);
$sessionControls->setGlobalSecureAccessFilteringProfile($sessionControlsGlobalSecureAccessFilteringProfile);
$requestBody->setSessionControls($sessionControls);
$requestBody->setState(new ConditionalAccessPolicyState('enabled'));

$result = $graphServiceClient->identity()->conditionalAccess()->policies()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Beta.Identity.SignIns

$params = @{
	conditions = @{
		applications = @{
			includeApplications = @(
			"5dc48733-b5df-475c-a49b-fa307ef00853"
		)
	}
	users = @{
		includeUsers = @(
		"00aa00aa-bb11-cc22-dd33-44ee44ee44ee"
	)
}
}
displayName = "UserA Access to AI and Bing"
sessionControls = @{
globalSecureAccessFilteringProfile = @{
	profileId = "dddddddd-9999-0000-1111-eeeeeeeeeeee"
	isEnabled = $true
}
}
state = "enabled"
}

New-MgBetaIdentityConditionalAccessPolicy -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph_beta import GraphServiceClient
from msgraph_beta.generated.models.conditional_access_policy import ConditionalAccessPolicy
from msgraph_beta.generated.models.conditional_access_condition_set import ConditionalAccessConditionSet
from msgraph_beta.generated.models.conditional_access_applications import ConditionalAccessApplications
from msgraph_beta.generated.models.conditional_access_users import ConditionalAccessUsers
from msgraph_beta.generated.models.conditional_access_session_controls import ConditionalAccessSessionControls
from msgraph_beta.generated.models.global_secure_access_filtering_profile_session_control import GlobalSecureAccessFilteringProfileSessionControl
from msgraph_beta.generated.models.conditional_access_policy_state import ConditionalAccessPolicyState
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ConditionalAccessPolicy(
	conditions = ConditionalAccessConditionSet(
		applications = ConditionalAccessApplications(
			include_applications = [\
				"5dc48733-b5df-475c-a49b-fa307ef00853",\
			],
		),
		users = ConditionalAccessUsers(
			include_users = [\
				"00aa00aa-bb11-cc22-dd33-44ee44ee44ee",\
			],
		),
	),
	display_name = "UserA Access to AI and Bing",
	session_controls = ConditionalAccessSessionControls(
		global_secure_access_filtering_profile = GlobalSecureAccessFilteringProfileSessionControl(
			profile_id = "dddddddd-9999-0000-1111-eeeeeeeeeeee",
			is_enabled = True,
		),
	),
	state = ConditionalAccessPolicyState.Enabled,
)

result = await graph_client.identity.conditional_access.policies.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
    "id": "9c5fbb22-30ff-4a17-9b83-ea9fbf2912a9",
    "templateId": null,
    "displayName": "UserA Access to AI and Bing",
    "createdDateTime": "2025-02-05T18:58:32.7622998Z",
    "modifiedDateTime": null,
    "state": "enabled",
    "grantControls": null,
    "partialEnablementStrategy": null,
    "conditions": {
        "userRiskLevels": [],
        "signInRiskLevels": [],
        "clientAppTypes": [\
            "all"\
        ],
        "platforms": null,
        "locations": null,
        "times": null,
        "deviceStates": null,
        "devices": null,
        "clientApplications": null,
        "applications": {
            "includeApplications": [\
                "5dc48733-b5df-475c-a49b-fa307ef00853"\
            ],
            "excludeApplications": [],
            "includeUserActions": [],
            "includeAuthenticationContextClassReferences": [],
            "applicationFilter": null
        },
        "users": {
            "includeUsers": [\
                "00aa00aa-bb11-cc22-dd33-44ee44ee44ee"\
            ],
            "excludeUsers": [],
            "includeGroups": [],
            "excludeGroups": [],
            "includeRoles": [],
            "excludeRoles": [],
            "includeGuestsOrExternalUsers": null,
            "excludeGuestsOrExternalUsers": null
        }
    },
    "sessionControls": {
        "disableResilienceDefaults": null,
        "applicationEnforcedRestrictions": null,
        "cloudAppSecurity": null,
        "signInFrequency": null,
        "persistentBrowser": null,
        "continuousAccessEvaluation": null,
        "secureSignInSession": null,
        "globalSecureAccessFilteringProfile": {
            "profileId": "dddddddd-9999-0000-1111-eeeeeeeeeeee",
            "isEnabled": true
        }
    }
}
```

## Conclusion

Now that you've configured a security profile or filtering profile blocking the Artificial Intelligence and `bing.com` for the sample user, that user is blocked from accessing those sites.

## Related content

- [Microsoft Security Service Edge Solution Deployment Guide for Microsoft Entra Internet Access Proof of Concept](https://learn.microsoft.com/en-us/entra/architecture/gsa-deployment-guide-internet-access)
- [Tutorial: Configure Microsoft Entra Internet Access using Microsoft Graph APIs](https://learn.microsoft.com/en-us/graph/tutorial-entra-internet-access)

* * *
