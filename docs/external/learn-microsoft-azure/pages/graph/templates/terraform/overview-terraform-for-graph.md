# Terraform for Microsoft Graph resources

The `msgraph` Terraform provider allows you to define the tenant infrastructure you want to deploy, such as groups or applications, in a Terraform configuration, then manage the development lifecycle of it as infrastructure. [Terraform](https://learn.microsoft.com/en-us/azure/developer/terraform/overview) is a domain-specific language (DSL) that uses declarative syntax to deploy resources, typically for your [infrastructure as code](https://learn.microsoft.com/en-us/devops/deliver/what-is-infrastructure-as-code) solutions.

Suppose you want to [call custom APIs from Azure Logic Apps](https://github.com/Azure/azure-quickstart-templates/tree/master/quickstarts/microsoft.logic/logic-app-custom-api) where the web app is secured using Microsoft Entra ID. To create the two application identities for the logic app and the web app, you can define the Microsoft Graph application and service principal resources in Terraform, instead of creating them manually beforehand. In the same file, you can define the logic app and web app resources. Then, you can repeatedly deploy the file throughout the development lifecycle and have confidence that all your Azure and Microsoft Graph resources are deployed consistently.

Important

The `msgraph` provider for Terraform is currently in PREVIEW.
See the [Supplemental Terms of Use for Microsoft Azure Previews](https://azure.microsoft.com/support/legal/preview-supplemental-terms/) for legal terms that apply to Azure features that are in beta, preview, or otherwise not yet released into general availability.

## Microsoft Graph Terraform provider

Historically, Terraform users could utilize the `azuread` provider to manage users, groups, service principals, and applications. The new `msgraph` provider also supports these features and extends functionality to all Microsoft Graph endpoints. These include new [Entra APIs like privileged identity management](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-apis) as well as [M365 Graph APIs like SharePoint sites](https://learn.microsoft.com/en-us/graph/api/resources/sharepoint).

- Azure customers can use familiar tools to deploy Azure resources together with the Microsoft Graph resources they depend on, such as applications and service principals, using infrastructure as code (IaC) and DevOps practices.
- It also opens the door for existing Microsoft Graph customers to use Terraform and IaC practices to deploy and manage their tenant's resources.

### Benefits of the `msgraph` Terraform provider

- **Day 0 support for beta and v1.0 API versions**: The `msgraph` provider allows you to reference both beta and v1.0 versions of supported Microsoft Graph resource types within the same Terraform file. Since support for resource types is automatic, you can access the latest features and functionality as soon as they're released via the provider.

- **Authoring experience**: You get a first-class authoring experience via the [Microsoft Terraform VSCode Extension](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-azureterraform) when you use it to create your Terraform `msgraph` configuration. The editor provides rich type-safety, intellisense, and syntax validation.

![Terraform file authoring example](https://learn.microsoft.com/en-us/graph/templates/terraform/media/graph-terraform-authoring.png)

- **Common and consistent development**: Terraform is multi-cloud and multi-provider. Using Terraform means you can define MSGraph resources to authenticate with Azure and create resources via the `azapi` or `azurerm` providers.

- **Full Terraform state file fidelity**: All set properties and values can be saved to state to ensure your team can effectively track drift of resources across their lifecycle.

## License requirements

Deploying Microsoft Graph resources using Terraform requires any licenses necessary to work with the Microsoft Graph resources you're deploying. A valid Azure subscription is required, if also deploying any Azure resources.

## Get started

### Try out your first quickstart

[Deploy your first Terraform configuration containing Microsoft Graph resources in minutes](https://learn.microsoft.com/en-us/graph/templates/terraform/quickstart-create-terraform)

### Learn more

#### Learn more about Terraform

1. Understand [Terraform](https://learn.microsoft.com/en-us/azure/developer/terraform/overview), its uses, and structure and syntax of Terraform files.
2. Explore [Learn modules for Terraform on Azure](https://learn.microsoft.com/en-us/training/paths/terraform-fundamentals/).

#### Learn more about Microsoft Graph

1. Learn about [Microsoft Graph](https://learn.microsoft.com/en-us/graph/overview).
2. Understand [authentication and authorization principles](https://learn.microsoft.com/en-us/graph/auth) in Microsoft Graph.
3. Try the [Microsoft Graph tutorials](https://learn.microsoft.com/en-us/graph/tutorials).

* * *
