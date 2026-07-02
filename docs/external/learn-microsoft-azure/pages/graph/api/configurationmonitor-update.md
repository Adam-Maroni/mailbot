# Update configurationMonitor

Namespace: microsoft.graph

Update the properties of a [configurationMonitor](https://learn.microsoft.com/en-us/graph/api/resources/configurationmonitor?view=graph-rest-1.0) object, including the monitor name, description, and baseline.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ❌ | ❌ | ❌ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | ConfigurationMonitoring.ReadWrite.All | Not available. |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | ConfigurationMonitoring.ReadWrite.All | Not available. |

## HTTP request

HTTP

Copy

```http
PATCH /admin/configurationManagement/configurationMonitors/{configurationMonitorId}
```

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |
| Content-Type | application/json. Required. |

## Request body

In the request body, supply _only_ the values for properties to update. Existing properties that aren't included in the request body maintain their previous values or are recalculated based on changes to other property values.

The following table specifies the properties that can be updated.

| Property | Type | Description |
| --- | --- | --- |
| baseline | [configurationBaseline](https://learn.microsoft.com/en-us/graph/api/resources/configurationbaseline?view=graph-rest-1.0) | This relationship defines details of at least one resource and one property associated with the resource to be monitored. When updating the baseline, you must provide the full baseline object. Optional. |
| description | String | User-friendly description of the monitor given by the user. Optional. |
| displayName | String | User-friendly name given by the user to the monitor. Optional. |
| parameters | [openComplexDictionaryType](https://learn.microsoft.com/en-us/graph/api/resources/opencomplexdictionarytype?view=graph-rest-1.0) | Key-value pairs that contain the values of parameters which might be used in the baseline. Optional. |
| status | monitorStatus | Status of the monitor. The possible values are: `active`, `inactive`, `unknownFutureValue`. Optional. |

## Response

If successful, this method returns a `204 No Content` response code.

## Examples

### Example 1: Update the displayName of a configurationMonitor

The following example shows how to update the **displayName** property of a **configurationMonitor** object.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

HTTP

Copy

```http
PATCH https://graph.microsoft.com/v1.0/admin/configurationManagement/configurationMonitors/b86049ce-0180-404e-803a-5616d49290d7
Content-Type: application/json

{
  "displayName": "Demo Monitor Name Change"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new ConfigurationMonitor
{
	DisplayName = "Demo Monitor Name Change",
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Admin.ConfigurationManagement.ConfigurationMonitors["{configurationMonitor-id}"].PatchAsync(requestBody);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

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

requestBody := graphmodels.NewConfigurationMonitor()
displayName := "Demo Monitor Name Change"
requestBody.SetDisplayName(&displayName)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
configurationMonitors, err := graphClient.Admin().ConfigurationManagement().ConfigurationMonitors().ByConfigurationMonitorId("configurationMonitor-id").Patch(context.Background(), requestBody, nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ConfigurationMonitor configurationMonitor = new ConfigurationMonitor();
configurationMonitor.setDisplayName("Demo Monitor Name Change");
ConfigurationMonitor result = graphClient.admin().configurationManagement().configurationMonitors().byConfigurationMonitorId("{configurationMonitor-id}").patch(configurationMonitor);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const configurationMonitor = {
  displayName: 'Demo Monitor Name Change'
};

await client.api('/admin/configurationManagement/configurationMonitors/b86049ce-0180-404e-803a-5616d49290d7')
	.update(configurationMonitor);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\ConfigurationMonitor;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ConfigurationMonitor();
$requestBody->setDisplayName('Demo Monitor Name Change');

$result = $graphServiceClient->admin()->configurationManagement()->configurationMonitors()->byConfigurationMonitorId('configurationMonitor-id')->patch($requestBody)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.ConfigurationManagement

$params = @{
	displayName = "Demo Monitor Name Change"
}

Update-MgAdminConfigurationManagementConfigurationMonitor -ConfigurationMonitorId $configurationMonitorId -BodyParameter $params
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.configuration_monitor import ConfigurationMonitor
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ConfigurationMonitor(
	display_name = "Demo Monitor Name Change",
)

result = await graph_client.admin.configuration_management.configuration_monitors.by_configuration_monitor_id('configurationMonitor-id').patch(request_body)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

HTTP

Copy

```http
HTTP/1.1 204 No Content
```

### Example 2: Update the baseline of a configurationMonitor

The following example shows how to update the **baseline** property of a **configurationMonitor** object. You must supply the full baseline object.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/configurationmonitor-update?view=graph-rest-1.0&tabs=http#tabpanel_2_python)

HTTP

Copy

```http
PATCH https://graph.microsoft.com/v1.0/admin/configurationManagement/configurationMonitors/b86049ce-0180-404e-803a-5616d49290d7
Content-Type: application/json

{
  "displayName": "Demo Monitor",
  "description": "This is a Demo Monitor",
  "baseline": {
    "displayName": "Demo Baseline",
    "description": "This is a baseline with SharedMailbox, AcceptedDomain and MailContact",
    "parameters": [\
      {\
        "displayName": "FQDN",\
        "description": "The Fully Qualified Domain Name of the Tenant",\
        "parameterType": "String"\
      }\
    ],
    "resources": [\
      {\
        "displayName": "TestSharedMailbox Resource",\
        "resourceType": "microsoft.exchange.sharedmailbox",\
        "properties": {\
          "DisplayName": "TestSharedMailbox",\
          "Identity": "TestSharedMailbox",\
          "Ensure": "Present",\
          "PrimarySmtpAddress": "[concat('testSharedMailbox', parameters('FQDN'))]",\
          "EmailAddresses": [\
            "abc@contoso.onmicrosoft.com",\
            "[concat('testSharedMailbox@', parameters('FQDN'))]"\
          ]\
        }\
      },\
      {\
        "displayName": "Accepted Domain",\
        "resourceType": "microsoft.exchange.accepteddomain",\
        "properties": {\
          "Identity": "contoso.onmicrosoft.com",\
          "DomainType": "InternalRelay",\
          "Ensure": "Present"\
        }\
      },\
      {\
        "displayName": "Mail Contact Resource",\
        "resourceType": "microsoft.exchange.mailcontact",\
        "properties": {\
          "Name": "Chris",\
          "DisplayName": "Chris",\
          "ExternalEmailAddress": "SMTP:chris@fabrikam.com",\
          "Alias": "Chrisa",\
          "Ensure": "Present"\
        }\
      }\
    ]
  },
  "parameters": {
    "FQDN": "contoso.onmicrosoft.com"
  }
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new ConfigurationMonitor
{
	DisplayName = "Demo Monitor",
	Description = "This is a Demo Monitor",
	Baseline = new ConfigurationBaseline
	{
		DisplayName = "Demo Baseline",
		Description = "This is a baseline with SharedMailbox, AcceptedDomain and MailContact",
		Parameters = new List<BaselineParameter>
		{
			new BaselineParameter
			{
				DisplayName = "FQDN",
				Description = "The Fully Qualified Domain Name of the Tenant",
				ParameterType = BaselineParameterType.String,
			},
		},
		Resources = new List<BaselineResource>
		{
			new BaselineResource
			{
				DisplayName = "TestSharedMailbox Resource",
				ResourceType = "microsoft.exchange.sharedmailbox",
				Properties = new OpenComplexDictionaryType
				{
					AdditionalData = new Dictionary<string, object>
					{
						{
							"DisplayName" , "TestSharedMailbox"
						},
						{
							"Identity" , "TestSharedMailbox"
						},
						{
							"Ensure" , "Present"
						},
						{
							"PrimarySmtpAddress" , "[concat('testSharedMailbox', parameters('FQDN'))]"
						},
						{
							"EmailAddresses" , new List<string>
							{
								"abc@contoso.onmicrosoft.com",
								"[concat('testSharedMailbox@', parameters('FQDN'))]",
							}
						},
					},
				},
			},
			new BaselineResource
			{
				DisplayName = "Accepted Domain",
				ResourceType = "microsoft.exchange.accepteddomain",
				Properties = new OpenComplexDictionaryType
				{
					AdditionalData = new Dictionary<string, object>
					{
						{
							"Identity" , "contoso.onmicrosoft.com"
						},
						{
							"DomainType" , "InternalRelay"
						},
						{
							"Ensure" , "Present"
						},
					},
				},
			},
			new BaselineResource
			{
				DisplayName = "Mail Contact Resource",
				ResourceType = "microsoft.exchange.mailcontact",
				Properties = new OpenComplexDictionaryType
				{
					AdditionalData = new Dictionary<string, object>
					{
						{
							"Name" , "Chris"
						},
						{
							"DisplayName" , "Chris"
						},
						{
							"ExternalEmailAddress" , "SMTP:chris@fabrikam.com"
						},
						{
							"Alias" , "Chrisa"
						},
						{
							"Ensure" , "Present"
						},
					},
				},
			},
		},
	},
	Parameters = new OpenComplexDictionaryType
	{
		AdditionalData = new Dictionary<string, object>
		{
			{
				"FQDN" , "contoso.onmicrosoft.com"
			},
		},
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Admin.ConfigurationManagement.ConfigurationMonitors["{configurationMonitor-id}"].PatchAsync(requestBody);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

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

requestBody := graphmodels.NewConfigurationMonitor()
displayName := "Demo Monitor"
requestBody.SetDisplayName(&displayName)
description := "This is a Demo Monitor"
requestBody.SetDescription(&description)
baseline := graphmodels.NewConfigurationBaseline()
displayName := "Demo Baseline"
baseline.SetDisplayName(&displayName)
description := "This is a baseline with SharedMailbox, AcceptedDomain and MailContact"
baseline.SetDescription(&description)

baselineParameter := graphmodels.NewBaselineParameter()
displayName := "FQDN"
baselineParameter.SetDisplayName(&displayName)
description := "The Fully Qualified Domain Name of the Tenant"
baselineParameter.SetDescription(&description)
parameterType := graphmodels.STRING_BASELINEPARAMETERTYPE
baselineParameter.SetParameterType(&parameterType)

parameters := []graphmodels.BaselineParameterable {
	baselineParameter,
}
baseline.SetParameters(parameters)

baselineResource := graphmodels.NewBaselineResource()
displayName := "TestSharedMailbox Resource"
baselineResource.SetDisplayName(&displayName)
resourceType := "microsoft.exchange.sharedmailbox"
baselineResource.SetResourceType(&resourceType)
properties := graphmodels.NewOpenComplexDictionaryType()
additionalData := map[string]interface{}{
	"DisplayName" : "TestSharedMailbox",
	"Identity" : "TestSharedMailbox",
	"Ensure" : "Present",
	"PrimarySmtpAddress" : "[concat('testSharedMailbox', parameters('FQDN'))]",
	emailAddresses := []string {
		"abc@contoso.onmicrosoft.com",
		"[concat('testSharedMailbox@', parameters('FQDN'))]",
	}
}
properties.SetAdditionalData(additionalData)
baselineResource.SetProperties(properties)
baselineResource1 := graphmodels.NewBaselineResource()
displayName := "Accepted Domain"
baselineResource1.SetDisplayName(&displayName)
resourceType := "microsoft.exchange.accepteddomain"
baselineResource1.SetResourceType(&resourceType)
properties := graphmodels.NewOpenComplexDictionaryType()
additionalData := map[string]interface{}{
	"Identity" : "contoso.onmicrosoft.com",
	"DomainType" : "InternalRelay",
	"Ensure" : "Present",
}
properties.SetAdditionalData(additionalData)
baselineResource1.SetProperties(properties)
baselineResource2 := graphmodels.NewBaselineResource()
displayName := "Mail Contact Resource"
baselineResource2.SetDisplayName(&displayName)
resourceType := "microsoft.exchange.mailcontact"
baselineResource2.SetResourceType(&resourceType)
properties := graphmodels.NewOpenComplexDictionaryType()
additionalData := map[string]interface{}{
	"Name" : "Chris",
	"DisplayName" : "Chris",
	"ExternalEmailAddress" : "SMTP:chris@fabrikam.com",
	"Alias" : "Chrisa",
	"Ensure" : "Present",
}
properties.SetAdditionalData(additionalData)
baselineResource2.SetProperties(properties)

resources := []graphmodels.BaselineResourceable {
	baselineResource,
	baselineResource1,
	baselineResource2,
}
baseline.SetResources(resources)
requestBody.SetBaseline(baseline)
parameters := graphmodels.NewOpenComplexDictionaryType()
additionalData := map[string]interface{}{
	"FQDN" : "contoso.onmicrosoft.com",
}
parameters.SetAdditionalData(additionalData)
requestBody.SetParameters(parameters)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
configurationMonitors, err := graphClient.Admin().ConfigurationManagement().ConfigurationMonitors().ByConfigurationMonitorId("configurationMonitor-id").Patch(context.Background(), requestBody, nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ConfigurationMonitor configurationMonitor = new ConfigurationMonitor();
configurationMonitor.setDisplayName("Demo Monitor");
configurationMonitor.setDescription("This is a Demo Monitor");
ConfigurationBaseline baseline = new ConfigurationBaseline();
baseline.setDisplayName("Demo Baseline");
baseline.setDescription("This is a baseline with SharedMailbox, AcceptedDomain and MailContact");
LinkedList<BaselineParameter> parameters = new LinkedList<BaselineParameter>();
BaselineParameter baselineParameter = new BaselineParameter();
baselineParameter.setDisplayName("FQDN");
baselineParameter.setDescription("The Fully Qualified Domain Name of the Tenant");
baselineParameter.setParameterType(BaselineParameterType.String);
parameters.add(baselineParameter);
baseline.setParameters(parameters);
LinkedList<BaselineResource> resources = new LinkedList<BaselineResource>();
BaselineResource baselineResource = new BaselineResource();
baselineResource.setDisplayName("TestSharedMailbox Resource");
baselineResource.setResourceType("microsoft.exchange.sharedmailbox");
OpenComplexDictionaryType properties = new OpenComplexDictionaryType();
HashMap<String, Object> additionalData = new HashMap<String, Object>();
additionalData.put("DisplayName", "TestSharedMailbox");
additionalData.put("Identity", "TestSharedMailbox");
additionalData.put("Ensure", "Present");
additionalData.put("PrimarySmtpAddress", "[concat('testSharedMailbox', parameters('FQDN'))]");
LinkedList<String> emailAddresses = new LinkedList<String>();
emailAddresses.add("abc@contoso.onmicrosoft.com");
emailAddresses.add("[concat('testSharedMailbox@', parameters('FQDN'))]");
additionalData.put("EmailAddresses", emailAddresses);
properties.setAdditionalData(additionalData);
baselineResource.setProperties(properties);
resources.add(baselineResource);
BaselineResource baselineResource1 = new BaselineResource();
baselineResource1.setDisplayName("Accepted Domain");
baselineResource1.setResourceType("microsoft.exchange.accepteddomain");
OpenComplexDictionaryType properties1 = new OpenComplexDictionaryType();
HashMap<String, Object> additionalData1 = new HashMap<String, Object>();
additionalData1.put("Identity", "contoso.onmicrosoft.com");
additionalData1.put("DomainType", "InternalRelay");
additionalData1.put("Ensure", "Present");
properties1.setAdditionalData(additionalData1);
baselineResource1.setProperties(properties1);
resources.add(baselineResource1);
BaselineResource baselineResource2 = new BaselineResource();
baselineResource2.setDisplayName("Mail Contact Resource");
baselineResource2.setResourceType("microsoft.exchange.mailcontact");
OpenComplexDictionaryType properties2 = new OpenComplexDictionaryType();
HashMap<String, Object> additionalData2 = new HashMap<String, Object>();
additionalData2.put("Name", "Chris");
additionalData2.put("DisplayName", "Chris");
additionalData2.put("ExternalEmailAddress", "SMTP:chris@fabrikam.com");
additionalData2.put("Alias", "Chrisa");
additionalData2.put("Ensure", "Present");
properties2.setAdditionalData(additionalData2);
baselineResource2.setProperties(properties2);
resources.add(baselineResource2);
baseline.setResources(resources);
configurationMonitor.setBaseline(baseline);
OpenComplexDictionaryType parameters1 = new OpenComplexDictionaryType();
HashMap<String, Object> additionalData3 = new HashMap<String, Object>();
additionalData3.put("FQDN", "contoso.onmicrosoft.com");
parameters1.setAdditionalData(additionalData3);
configurationMonitor.setParameters(parameters1);
ConfigurationMonitor result = graphClient.admin().configurationManagement().configurationMonitors().byConfigurationMonitorId("{configurationMonitor-id}").patch(configurationMonitor);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const configurationMonitor = {
  displayName: 'Demo Monitor',
  description: 'This is a Demo Monitor',
  baseline: {
    displayName: 'Demo Baseline',
    description: 'This is a baseline with SharedMailbox, AcceptedDomain and MailContact',
    parameters: [\
      {\
        displayName: 'FQDN',\
        description: 'The Fully Qualified Domain Name of the Tenant',\
        parameterType: 'String'\
      }\
    ],
    resources: [\
      {\
        displayName: 'TestSharedMailbox Resource',\
        resourceType: 'microsoft.exchange.sharedmailbox',\
        properties: {\
          DisplayName: 'TestSharedMailbox',\
          Identity: 'TestSharedMailbox',\
          Ensure: 'Present',\
          PrimarySmtpAddress: '[concat(\'testSharedMailbox\', parameters(\'FQDN\'))]',\
          EmailAddresses: [\
            'abc@contoso.onmicrosoft.com',\
            '[concat(\'testSharedMailbox@\', parameters(\'FQDN\'))]'\
          ]\
        }\
      },\
      {\
        displayName: 'Accepted Domain',\
        resourceType: 'microsoft.exchange.accepteddomain',\
        properties: {\
          Identity: 'contoso.onmicrosoft.com',\
          DomainType: 'InternalRelay',\
          Ensure: 'Present'\
        }\
      },\
      {\
        displayName: 'Mail Contact Resource',\
        resourceType: 'microsoft.exchange.mailcontact',\
        properties: {\
          Name: 'Chris',\
          DisplayName: 'Chris',\
          ExternalEmailAddress: 'SMTP:chris@fabrikam.com',\
          Alias: 'Chrisa',\
          Ensure: 'Present'\
        }\
      }\
    ]
  },
  parameters: {
    FQDN: 'contoso.onmicrosoft.com'
  }
};

await client.api('/admin/configurationManagement/configurationMonitors/b86049ce-0180-404e-803a-5616d49290d7')
	.update(configurationMonitor);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\ConfigurationMonitor;
use Microsoft\Graph\Generated\Models\ConfigurationBaseline;
use Microsoft\Graph\Generated\Models\BaselineParameter;
use Microsoft\Graph\Generated\Models\BaselineParameterType;
use Microsoft\Graph\Generated\Models\BaselineResource;
use Microsoft\Graph\Generated\Models\OpenComplexDictionaryType;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ConfigurationMonitor();
$requestBody->setDisplayName('Demo Monitor');
$requestBody->setDescription('This is a Demo Monitor');
$baseline = new ConfigurationBaseline();
$baseline->setDisplayName('Demo Baseline');
$baseline->setDescription('This is a baseline with SharedMailbox, AcceptedDomain and MailContact');
$parametersBaselineParameter1 = new BaselineParameter();
$parametersBaselineParameter1->setDisplayName('FQDN');
$parametersBaselineParameter1->setDescription('The Fully Qualified Domain Name of the Tenant');
$parametersBaselineParameter1->setParameterType(new BaselineParameterType('string'));
$parametersArray []= $parametersBaselineParameter1;
$baseline->setParameters($parametersArray);

$resourcesBaselineResource1 = new BaselineResource();
$resourcesBaselineResource1->setDisplayName('TestSharedMailbox Resource');
$resourcesBaselineResource1->setResourceType('microsoft.exchange.sharedmailbox');
$resourcesBaselineResource1Properties = new OpenComplexDictionaryType();
$additionalData = [\
'DisplayName' => 'TestSharedMailbox',\
'Identity' => 'TestSharedMailbox',\
'Ensure' => 'Present',\
'PrimarySmtpAddress' => '[concat(\'testSharedMailbox\', parameters(\'FQDN\'))]',\
'EmailAddresses' => [\
'abc@contoso.onmicrosoft.com', '[concat(\'testSharedMailbox@\', parameters(\'FQDN\'))]', ],\
];
$resourcesBaselineResource1Properties->setAdditionalData($additionalData);
$resourcesBaselineResource1->setProperties($resourcesBaselineResource1Properties);
$resourcesArray []= $resourcesBaselineResource1;
$resourcesBaselineResource2 = new BaselineResource();
$resourcesBaselineResource2->setDisplayName('Accepted Domain');
$resourcesBaselineResource2->setResourceType('microsoft.exchange.accepteddomain');
$resourcesBaselineResource2Properties = new OpenComplexDictionaryType();
$additionalData = [\
'Identity' => 'contoso.onmicrosoft.com',\
'DomainType' => 'InternalRelay',\
'Ensure' => 'Present',\
];
$resourcesBaselineResource2Properties->setAdditionalData($additionalData);
$resourcesBaselineResource2->setProperties($resourcesBaselineResource2Properties);
$resourcesArray []= $resourcesBaselineResource2;
$resourcesBaselineResource3 = new BaselineResource();
$resourcesBaselineResource3->setDisplayName('Mail Contact Resource');
$resourcesBaselineResource3->setResourceType('microsoft.exchange.mailcontact');
$resourcesBaselineResource3Properties = new OpenComplexDictionaryType();
$additionalData = [\
'Name' => 'Chris',\
'DisplayName' => 'Chris',\
'ExternalEmailAddress' => 'SMTP:chris@fabrikam.com',\
'Alias' => 'Chrisa',\
'Ensure' => 'Present',\
];
$resourcesBaselineResource3Properties->setAdditionalData($additionalData);
$resourcesBaselineResource3->setProperties($resourcesBaselineResource3Properties);
$resourcesArray []= $resourcesBaselineResource3;
$baseline->setResources($resourcesArray);

$requestBody->setBaseline($baseline);
$parameters = new OpenComplexDictionaryType();
$additionalData = [\
'FQDN' => 'contoso.onmicrosoft.com',\
];
$parameters->setAdditionalData($additionalData);
$requestBody->setParameters($parameters);

$result = $graphServiceClient->admin()->configurationManagement()->configurationMonitors()->byConfigurationMonitorId('configurationMonitor-id')->patch($requestBody)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.ConfigurationManagement

$params = @{
	displayName = "Demo Monitor"
	description = "This is a Demo Monitor"
	baseline = @{
		displayName = "Demo Baseline"
		description = "This is a baseline with SharedMailbox, AcceptedDomain and MailContact"
		parameters = @(
			@{
				displayName = "FQDN"
				description = "The Fully Qualified Domain Name of the Tenant"
				parameterType = "String"
			}
		)
		resources = @(
			@{
				displayName = "TestSharedMailbox Resource"
				resourceType = "microsoft.exchange.sharedmailbox"
				properties = @{
					DisplayName = "TestSharedMailbox"
					Identity = "TestSharedMailbox"
					Ensure = "Present"
					PrimarySmtpAddress = "[concat('testSharedMailbox', parameters('FQDN'))]"
					EmailAddresses = @(
					"abc@contoso.onmicrosoft.com"
				"[concat('testSharedMailbox@', parameters('FQDN'))]"
			)
		}
	}
	@{
		displayName = "Accepted Domain"
		resourceType = "microsoft.exchange.accepteddomain"
		properties = @{
			Identity = "contoso.onmicrosoft.com"
			DomainType = "InternalRelay"
			Ensure = "Present"
		}
	}
	@{
		displayName = "Mail Contact Resource"
		resourceType = "microsoft.exchange.mailcontact"
		properties = @{
			Name = "Chris"
			DisplayName = "Chris"
			ExternalEmailAddress = "SMTP:chris@fabrikam.com"
			Alias = "Chrisa"
			Ensure = "Present"
		}
	}
)
}
parameters = @{
FQDN = "contoso.onmicrosoft.com"
}
}

Update-MgAdminConfigurationManagementConfigurationMonitor -ConfigurationMonitorId $configurationMonitorId -BodyParameter $params
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.configuration_monitor import ConfigurationMonitor
from msgraph.generated.models.configuration_baseline import ConfigurationBaseline
from msgraph.generated.models.baseline_parameter import BaselineParameter
from msgraph.generated.models.baseline_parameter_type import BaselineParameterType
from msgraph.generated.models.baseline_resource import BaselineResource
from msgraph.generated.models.open_complex_dictionary_type import OpenComplexDictionaryType
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ConfigurationMonitor(
	display_name = "Demo Monitor",
	description = "This is a Demo Monitor",
	baseline = ConfigurationBaseline(
		display_name = "Demo Baseline",
		description = "This is a baseline with SharedMailbox, AcceptedDomain and MailContact",
		parameters = [\
			BaselineParameter(\
				display_name = "FQDN",\
				description = "The Fully Qualified Domain Name of the Tenant",\
				parameter_type = BaselineParameterType.String,\
			),\
		],
		resources = [\
			BaselineResource(\
				display_name = "TestSharedMailbox Resource",\
				resource_type = "microsoft.exchange.sharedmailbox",\
				properties = OpenComplexDictionaryType(\
					additional_data = {\
							"display_name" : "TestSharedMailbox",\
							"identity" : "TestSharedMailbox",\
							"ensure" : "Present",\
							"primary_smtp_address" : "[concat('testSharedMailbox', parameters('FQDN'))]",\
							"email_addresses" : [\
								"abc@contoso.onmicrosoft.com",\
								"[concat('testSharedMailbox@', parameters('FQDN'))]",\
							],\
					}\
				),\
			),\
			BaselineResource(\
				display_name = "Accepted Domain",\
				resource_type = "microsoft.exchange.accepteddomain",\
				properties = OpenComplexDictionaryType(\
					additional_data = {\
							"identity" : "contoso.onmicrosoft.com",\
							"domain_type" : "InternalRelay",\
							"ensure" : "Present",\
					}\
				),\
			),\
			BaselineResource(\
				display_name = "Mail Contact Resource",\
				resource_type = "microsoft.exchange.mailcontact",\
				properties = OpenComplexDictionaryType(\
					additional_data = {\
							"name" : "Chris",\
							"display_name" : "Chris",\
							"external_email_address" : "SMTP:chris@fabrikam.com",\
							"alias" : "Chrisa",\
							"ensure" : "Present",\
					}\
				),\
			),\
		],
	),
	parameters = OpenComplexDictionaryType(
		additional_data = {
				"f_q_d_n" : "contoso.onmicrosoft.com",
		}
	),
)

result = await graph_client.admin.configuration_management.configuration_monitors.by_configuration_monitor_id('configurationMonitor-id').patch(request_body)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

HTTP

Copy

```http
HTTP/1.1 204 No Content
```

* * *
