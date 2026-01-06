import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SSOConfigSettings } from './sso-config-settings'
import { DomainClaimsSettings } from './domain-claims-settings'
import { SCIMTokensSettings } from './scim-tokens-settings'

/**
 * SSO settings component without page header.
 * Used in Admin page tabs.
 */
export function SSOSettings() {
  return (
    <Tabs defaultValue="config" className="space-y-4">
      <TabsList>
        <TabsTrigger value="config">SSO Configuration</TabsTrigger>
        <TabsTrigger value="domains">Domain Claims</TabsTrigger>
        <TabsTrigger value="scim">SCIM Provisioning</TabsTrigger>
      </TabsList>

      <TabsContent value="config" className="space-y-4">
        <SSOConfigSettings />
      </TabsContent>

      <TabsContent value="domains" className="space-y-4">
        <DomainClaimsSettings />
      </TabsContent>

      <TabsContent value="scim" className="space-y-4">
        <SCIMTokensSettings />
      </TabsContent>
    </Tabs>
  )
}
