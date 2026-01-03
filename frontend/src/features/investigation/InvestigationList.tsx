import { Link } from 'react-router-dom'
import { useInvestigations } from '@/lib/api/investigations'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { formatDate } from '@/lib/utils'
import { Plus, RefreshCw } from 'lucide-react'

function getStatusVariant(status: string) {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'destructive'
    case 'started':
    case 'in_progress':
      return 'warning'
    default:
      return 'secondary'
  }
}

export function InvestigationList() {
  const { data: investigations, isLoading, error, refetch } = useInvestigations()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">
            Failed to load investigations: {error.message}
          </p>
          <Button onClick={() => refetch()} className="mt-4">
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Investigations</h1>
        <Link to="/investigations/new">
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            New Investigation
          </Button>
        </Link>
      </div>

      {investigations?.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">No investigations yet.</p>
            <Link to="/investigations/new">
              <Button className="mt-4">Create your first investigation</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {investigations?.map((inv) => (
            <Link key={inv.investigation_id} to={`/investigations/${inv.investigation_id}`}>
              <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">
                      {inv.dataset_id}
                    </CardTitle>
                    <Badge variant={getStatusVariant(inv.status)}>
                      {inv.status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Created: {formatDate(inv.created_at)}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
