# billedUsage: export

Namespace: microsoft.graph.partners.billing

This API is available for Cloud Solution Provider (CSP) partners only to access their billed and unbilled reconciliation data for a tenant. To learn more about the CSP program, see [Microsoft Cloud Solution Provider](https://learn.microsoft.com/en-us/partner-center/csp-overview).

Export the billed Azure usage data.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ❌ | ❌ | ❌ |

## Permissions

One of the following permissions is required to call this API. To learn more, including how to choose permissions, see [Permissions](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | PartnerBilling.Read.All | Not available. |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | PartnerBilling.Read.All | Not available. |

## HTTP request

HTTP

Copy

```http
POST /reports/partners/billing/usage/billed/export
```

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |
| Content-Type | application/json. Required. |

## Request body

In the request body, supply a JSON representation of the parameters.

The following table shows the parameters that you can use with this action.

| Parameter | Type | Description |
| --- | --- | --- |
| attributeSet | [microsoft.graph.partners.billing.attributeSet](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-attributeset?view=graph-rest-1.0) | Attributes that should be exported. The possible values are: `full`, `basic`, `unknownFutureValue`. The default value is `full`. Choose `full` for a complete response or `basic` for a subset of attributes. Optional. |
| invoiceId | String | The invoice ID for which the partner requested to export data. Required. |

## Response

If successful, this method returns a `202 Accepted` response code and a `Location` header that contains the URL to the long-running operation. You can check the status of the long-running operation by making a GET request to this URL that returns one of the following objects in the response body: [microsoft.graph.partners.billing.runningOperation](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-runningoperation?view=graph-rest-1.0), [microsoft.graph.partners.billing.exportSuccessOperation](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-exportsuccessoperation?view=graph-rest-1.0), or [microsoft.graph.partners.billing.failedOperation](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-failedoperation?view=graph-rest-1.0).

## Examples

### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/partners-billing-billedusage-export?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/reports/partners/billing/usage/billed/export
Content-Type: application/json

{
  "invoiceId" : "G016907411",
  "attributeSet" : "full"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Reports.Partners.Billing.Usage.Billed.MicrosoftGraphPartnersBillingExport;
using Microsoft.Graph.Models.Partners.Billing;

var requestBody = new ExportPostRequestBody
{
	InvoiceId = "G016907411",
	AttributeSet = AttributeSet.Full,
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Reports.Partners.Billing.Usage.Billed.MicrosoftGraphPartnersBillingExport.PostAsync(requestBody);
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
	  graphreports "github.com/microsoftgraph/msgraph-sdk-go/reports"
	  graphmodelspartnersbilling "github.com/microsoftgraph/msgraph-sdk-go/models/partners/billing"
	  //other-imports
)

requestBody := graphreports.NewExportPostRequestBody()
invoiceId := "G016907411"
requestBody.SetInvoiceId(&invoiceId)
attributeSet := graphmodels.FULL_ATTRIBUTESET
requestBody.SetAttributeSet(&attributeSet)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
microsoftGraphPartnersBillingExport, err := graphClient.Reports().Partners().Billing().Usage().Billed().MicrosoftGraphPartnersBillingExport().Post(context.Background(), requestBody, nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.reports.partners.billing.usage.billed.microsoftgraphpartnersbillingexport.ExportPostRequestBody exportPostRequestBody = new com.microsoft.graph.reports.partners.billing.usage.billed.microsoftgraphpartnersbillingexport.ExportPostRequestBody();
exportPostRequestBody.setInvoiceId("G016907411");
exportPostRequestBody.setAttributeSet(com.microsoft.graph.models.partners.billing.AttributeSet.Full);
var result = graphClient.reports().partners().billing().usage().billed().microsoftGraphPartnersBillingExport().post(exportPostRequestBody);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const operation = {
  invoiceId: 'G016907411',
  attributeSet: 'full'
};

await client.api('/reports/partners/billing/usage/billed/export')
	.post(operation);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Reports\Partners\Billing\Usage\Billed\MicrosoftGraphPartnersBillingExport\ExportPostRequestBody;
use Microsoft\Graph\Generated\Models\Partners\Billing\AttributeSet;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ExportPostRequestBody();
$requestBody->setInvoiceId('G016907411');
$requestBody->setAttributeSet(new AttributeSet('full'));

$result = $graphServiceClient->reports()->partners()->billing()->usage()->billed()->microsoftGraphPartnersBillingExport()->post($requestBody)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Reports

$params = @{
	invoiceId = "G016907411"
	attributeSet = "full"
}

Export-MgReportPartnerBillingUsageBilled -BodyParameter $params
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.reports.partners.billing.usage.billed.microsoft_graph_partners_billing_export.export_post_request_body import ExportPostRequestBody
from msgraph.generated.models.attribute_set import AttributeSet
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ExportPostRequestBody(
	invoice_id = "G016907411",
	attribute_set = AttributeSet.Full,
)

result = await graph_client.reports.partners.billing.usage.billed.microsoft_graph_partners_billing_export.post(request_body)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

### Response

The following example shows the response.

HTTP

Copy

```http
HTTP/1.1 202 Accepted
Location: https://graph.microsoft.com/v1.0/reports/partners/billing/operations/9ab9cb54-d07f-4f52-9ea6-a09d7de52c14
```

* * *
