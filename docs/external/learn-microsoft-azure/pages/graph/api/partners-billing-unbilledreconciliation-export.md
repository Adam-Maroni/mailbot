# unbilledReconciliation: export

Namespace: microsoft.graph.partners.billing

This API is available for Cloud Solution Provider (CSP) partners only to access their billed and unbilled reconciliation data for a tenant. To learn more about the CSP program, see [Microsoft Cloud Solution Provider](https://learn.microsoft.com/en-us/partner-center/csp-overview).

Export the unbilled invoice reconciliation data for a specific billing period and a given currency.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ❌ | ❌ | ❌ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | PartnerBilling.Read.All | Not available. |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | PartnerBilling.Read.All | Not available. |

## HTTP request

HTTP

Copy

```http
POST /reports/partners/billing/reconciliation/unbilled/export
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
| billingPeriod | [microsoft.graph.partners.billing.billingPeriod](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-unbilledusage?view=graph-rest-1.0#billingperiod-values) | The billing period for the export data. The possible values are: `current`, `last`, `unknownFutureValue`. Choose `current` for the current billing period and `last` for the last billing period. Required. |
| currencyCode | String | The currency code for the partner billing. Required. |

## Response

If successful, this method returns a `202 Accepted` response code and a `Location` header that contains the URL to the long-running operation. You can check the status of the long-running operation by making a GET request to this URL that returns one of the following objects in the response body: [microsoft.graph.partners.billing.runningOperation](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-runningoperation?view=graph-rest-1.0), [microsoft.graph.partners.billing.exportSuccessOperation](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-exportsuccessoperation?view=graph-rest-1.0), or [microsoft.graph.partners.billing.failedOperation](https://learn.microsoft.com/en-us/graph/api/resources/partners-billing-failedoperation?view=graph-rest-1.0).

## Examples

### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/partners-billing-unbilledreconciliation-export?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/reports/partners/billing/reconciliation/unbilled/export
Content-Type: application/json

{
  "attributeSet": "full",
  "billingPeriod": "current",
  "currencyCode": "USD"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Reports.Partners.Billing.Reconciliation.Unbilled.MicrosoftGraphPartnersBillingExport;
using Microsoft.Graph.Models.Partners.Billing;

var requestBody = new ExportPostRequestBody
{
	AttributeSet = AttributeSet.Full,
	BillingPeriod = BillingPeriod.Current,
	CurrencyCode = "USD",
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Reports.Partners.Billing.Reconciliation.Unbilled.MicrosoftGraphPartnersBillingExport.PostAsync(requestBody);
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
attributeSet := graphmodels.FULL_ATTRIBUTESET
requestBody.SetAttributeSet(&attributeSet)
billingPeriod := graphmodels.CURRENT_BILLINGPERIOD
requestBody.SetBillingPeriod(&billingPeriod)
currencyCode := "USD"
requestBody.SetCurrencyCode(&currencyCode)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
microsoftGraphPartnersBillingExport, err := graphClient.Reports().Partners().Billing().Reconciliation().Unbilled().MicrosoftGraphPartnersBillingExport().Post(context.Background(), requestBody, nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.reports.partners.billing.reconciliation.unbilled.microsoftgraphpartnersbillingexport.ExportPostRequestBody exportPostRequestBody = new com.microsoft.graph.reports.partners.billing.reconciliation.unbilled.microsoftgraphpartnersbillingexport.ExportPostRequestBody();
exportPostRequestBody.setAttributeSet(com.microsoft.graph.models.partners.billing.AttributeSet.Full);
exportPostRequestBody.setBillingPeriod(com.microsoft.graph.models.partners.billing.BillingPeriod.Current);
exportPostRequestBody.setCurrencyCode("USD");
var result = graphClient.reports().partners().billing().reconciliation().unbilled().microsoftGraphPartnersBillingExport().post(exportPostRequestBody);
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
  attributeSet: 'full',
  billingPeriod: 'current',
  currencyCode: 'USD'
};

await client.api('/reports/partners/billing/reconciliation/unbilled/export')
	.post(operation);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Reports\Partners\Billing\Reconciliation\Unbilled\MicrosoftGraphPartnersBillingExport\ExportPostRequestBody;
use Microsoft\Graph\Generated\Models\Partners\Billing\AttributeSet;
use Microsoft\Graph\Generated\Models\Partners\Billing\BillingPeriod;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ExportPostRequestBody();
$requestBody->setAttributeSet(new AttributeSet('full'));
$requestBody->setBillingPeriod(new BillingPeriod('current'));
$requestBody->setCurrencyCode('USD');

$result = $graphServiceClient->reports()->partners()->billing()->reconciliation()->unbilled()->microsoftGraphPartnersBillingExport()->post($requestBody)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Reports

$params = @{
	attributeSet = "full"
	billingPeriod = "current"
	currencyCode = "USD"
}

Export-MgReportPartnerBillingReconciliationUnbilled -BodyParameter $params
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.reports.partners.billing.reconciliation.unbilled.microsoft_graph_partners_billing_export.export_post_request_body import ExportPostRequestBody
from msgraph.generated.models.attribute_set import AttributeSet
from msgraph.generated.models.billing_period import BillingPeriod
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ExportPostRequestBody(
	attribute_set = AttributeSet.Full,
	billing_period = BillingPeriod.Current,
	currency_code = "USD",
)

result = await graph_client.reports.partners.billing.reconciliation.unbilled.microsoft_graph_partners_billing_export.post(request_body)
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
