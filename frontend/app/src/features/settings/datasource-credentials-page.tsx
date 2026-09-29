/**
 * A person's own login for one datasource (spec 0001 D3), laid out like the
 * sign-in page. The issue agent links here when a question needs a login it
 * doesn't have. Saving checks the login against the database first, then
 * returns the person to the page they came from, such as the issue thread.
 */

import * as React from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Building, KeyRound, Lock, User, Warehouse } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/Button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/label";
import {
  useCredentialsStatus,
  useDeleteCredentials,
  useSaveCredentials,
} from "@/lib/api/credentials";
import { useDataSource, useSourceTypes } from "@/lib/api/datasources";
import { errorText } from "@/lib/api/error-message";

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center p-4">
      {children}
    </div>
  );
}

export function DatasourceCredentialsPage() {
  const { datasourceId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const datasource = useDataSource(datasourceId);
  const sourceTypes = useSourceTypes();
  const status = useCredentialsStatus(datasourceId);

  // Back to the page that linked here; a page opened directly has none
  const goBack = () => {
    if (location.key !== "default") navigate(-1);
    else navigate("/datasources");
  };

  if (datasource.isLoading || sourceTypes.isLoading || status.isLoading) {
    return (
      <Centered>
        <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
      </Centered>
    );
  }

  if (!datasource.data) {
    return (
      <Centered>
        <Card className="w-full max-w-md text-center">
          <CardHeader>
            <CardTitle className="text-xl">Datasource not found</CardTitle>
            <CardDescription>
              It may have been removed, or it belongs to another organization.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link to="/datasources" className="text-sm text-primary underline">
              See your datasources
            </Link>
          </CardContent>
        </Card>
      </Centered>
    );
  }

  const { name, type } = datasource.data;
  // The login fields this kind of source takes. If the types didn't load, the
  // server still refuses a source with no login when the form is sent.
  const fields = sourceTypes.data?.find((t) => t.type === type)?.config_schema
    .fields;
  const takes = (field: string) =>
    fields ? fields.some((f) => f.name === field) : field === "username";

  return (
    <Centered>
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <div className="mb-4 flex justify-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <KeyRound className="h-6 w-6" />
            </div>
          </div>
          <CardTitle className="text-2xl font-bold">
            Connect to {name}
          </CardTitle>
          <CardDescription>
            Sign in with your own database login. The issue agent runs your
            questions with it, so you only see what the database lets you see.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {takes("username") ? (
            <LoginForm
              datasourceId={datasourceId}
              name={name}
              connectedAs={
                status.data?.configured
                  ? (status.data.db_username ?? "your saved login")
                  : null
              }
              askRole={takes("role")}
              askWarehouse={takes("warehouse")}
              onSaved={goBack}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              {name} has no database login, so there is nothing to add here. The
              issue agent can't query it yet.
            </p>
          )}
          <div className="mt-4 text-center">
            <Button
              type="button"
              variant="link"
              className="h-auto p-0 text-xs text-muted-foreground"
              onClick={goBack}
            >
              Back
            </Button>
          </div>
        </CardContent>
      </Card>
    </Centered>
  );
}

interface LoginFormProps {
  datasourceId: string;
  name: string;
  /** The saved login's database user, or null when there is none. */
  connectedAs: string | null;
  askRole: boolean;
  askWarehouse: boolean;
  onSaved: () => void;
}

function LoginForm({
  datasourceId,
  name,
  connectedAs,
  askRole,
  askWarehouse,
  onSaved,
}: LoginFormProps) {
  const save = useSaveCredentials(datasourceId);
  const remove = useDeleteCredentials(datasourceId);
  const [username, setUsername] = React.useState(connectedAs ?? "");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState("");
  const [warehouse, setWarehouse] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const user = username.trim();
    try {
      await save.mutateAsync({
        username: user,
        password,
        role: role.trim() || null,
        warehouse: warehouse.trim() || null,
      });
      setPassword("");
      toast.success(`Connected to ${name} as ${user}`, {
        description: "Ask the agent again. It uses this login from now on.",
      });
      onSaved();
    } catch (err) {
      setError(errorText(err));
    }
  };

  const handleRemove = async () => {
    setError(null);
    try {
      await remove.mutateAsync();
      toast.success(`Removed your login for ${name}`);
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <>
      {connectedAs && (
        <p className="mb-4 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
          You're connected as <span className="font-medium">{connectedAs}</span>
          . Enter a login to replace it.
        </p>
      )}
      <form
        onSubmit={handleSubmit}
        className="space-y-4"
        aria-label={`Your login for ${name}`}
      >
        <div className="space-y-2">
          <Label htmlFor="credentials-username">Username</Label>
          <div className="relative">
            <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              id="credentials-username"
              placeholder="Your database user"
              autoComplete="off"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="pl-9"
              required
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="credentials-password">Password</Label>
          <div className="relative">
            <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              id="credentials-password"
              type="password"
              placeholder="••••••••"
              // Not the Dataing sign-in, which the browser would offer here
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="pl-9"
              required
            />
          </div>
        </div>

        {askRole && (
          <div className="space-y-2">
            <Label htmlFor="credentials-role">Role (optional)</Label>
            <div className="relative">
              <Building className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                id="credentials-role"
                placeholder="Your default role if empty"
                autoComplete="off"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
        )}

        {askWarehouse && (
          <div className="space-y-2">
            <Label htmlFor="credentials-warehouse">Warehouse (optional)</Label>
            <div className="relative">
              <Warehouse className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                id="credentials-warehouse"
                placeholder="The datasource's warehouse if empty"
                autoComplete="off"
                value={warehouse}
                onChange={(e) => setWarehouse(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
        )}

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <Button
          type="submit"
          className="w-full"
          disabled={save.isPending || !username.trim() || !password}
        >
          {save.isPending
            ? "Checking your login..."
            : connectedAs
              ? "Replace login"
              : "Connect"}
        </Button>
      </form>

      {connectedAs && (
        <Button
          type="button"
          variant="ghost"
          className="mt-2 w-full text-destructive hover:text-destructive"
          disabled={remove.isPending}
          onClick={() => void handleRemove()}
        >
          Remove my login
        </Button>
      )}
    </>
  );
}
