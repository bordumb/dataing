import { Card } from "@/components/ui/Card";
import { getSharedInvestigation } from "@/lib/api/share";

interface PageProps {
  params: Promise<{ token: string }>;
}

export default async function SharedInvestigationPage({ params }: PageProps) {
  const { token } = await params;

  let investigation;
  let error: string | null = null;

  try {
    investigation = await getSharedInvestigation(token);
  } catch (err) {
    error = err instanceof Error ? err.message : "Failed to load shared investigation";
  }

  if (error || !investigation) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <Card title="Share Link Not Found">
          <div className="text-center space-y-4">
            <p className="text-gray-600">
              {error || "This share link may have expired or does not exist."}
            </p>
            <a
              href="https://datadr.io"
              className="inline-block text-blue-600 hover:text-blue-800 font-medium"
            >
              Learn more about DataDr →
            </a>
          </div>
        </Card>
      </div>
    );
  }

  // Parse JSON fields
  let inputContext: any = {};
  let result: any = {};

  try {
    inputContext = investigation.input_context ? JSON.parse(investigation.input_context) : {};
  } catch (e) {
    console.error("Failed to parse input_context:", e);
  }

  try {
    result = investigation.result ? JSON.parse(investigation.result) : {};
  } catch (e) {
    console.error("Failed to parse result:", e);
  }

  const isComplete = investigation.status === "completed";
  const statusColor = isComplete ? "text-green-600" : investigation.status === "failed" ? "text-red-600" : "text-yellow-600";
  const datasetList = Array.isArray(inputContext.datasets)
    ? inputContext.datasets
    : Array.isArray(inputContext.all_datasets)
      ? inputContext.all_datasets
      : null;
  const datasetDisplay = datasetList
    ? datasetList.map((entry: any) => entry?.identifier).filter(Boolean).join(", ")
    : inputContext.table_name || inputContext.dataset_name || "Unknown";

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                Investigation Shared via DataDr
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                Shared by {investigation.user_name || "Unknown"}
              </p>
            </div>
            <a
              href="https://datadr.io/signup"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
            >
              Get DataDr Free
            </a>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        {/* Status Card */}
        <Card title="Investigation Status">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-gray-500">Status</p>
              <p className={`font-medium ${statusColor}`}>
                {investigation.status.charAt(0).toUpperCase() + investigation.status.slice(1)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Anomaly Type</p>
              <p className="font-medium text-gray-900">
                {investigation.anomaly_type || "Unknown"}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Dataset</p>
              <p className="font-medium text-gray-900">
                {datasetDisplay}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Created</p>
              <p className="font-medium text-gray-900">
                {investigation.created_at
                  ? new Date(investigation.created_at).toLocaleDateString()
                  : "Unknown"}
              </p>
            </div>
          </div>
        </Card>

        {/* Diagnosis Card */}
        {isComplete && result.root_cause && (
          <Card title="AI Diagnosis">
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">Root Cause</h3>
                <p className="text-gray-900">{result.root_cause}</p>
              </div>
              {result.summary && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 mb-2">Summary</h3>
                  <p className="text-gray-900">{result.summary}</p>
                </div>
              )}
              {result.confidence !== undefined && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 mb-2">Confidence</h3>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-blue-600 h-2 rounded-full"
                        style={{ width: `${result.confidence * 100}%` }}
                      />
                    </div>
                    <span className="text-sm font-medium text-gray-900">
                      {Math.round(result.confidence * 100)}%
                    </span>
                  </div>
                </div>
              )}
            </div>
          </Card>
        )}

        {/* In Progress Message */}
        {!isComplete && (
          <Card title="Investigation In Progress">
            <p className="text-gray-600">
              This investigation is still running. The full diagnosis will be available once complete.
            </p>
          </Card>
        )}

        {/* CTA Card */}
        <Card title="Get DataDr for Your Team">
          <div className="space-y-4">
            <p className="text-gray-700">
              DataDr automatically investigates data quality issues in your pipelines,
              saving your team hours of manual debugging.
            </p>
            <div className="flex gap-4">
              <a
                href="https://datadr.io/signup"
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
              >
                Start Free Trial →
              </a>
              <a
                href="https://datadr.io/demo"
                className="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium"
              >
                Book a Demo
              </a>
            </div>
          </div>
        </Card>
      </div>

      {/* Footer */}
      <div className="max-w-6xl mx-auto px-4 py-8 border-t border-gray-200 mt-12">
        <p className="text-center text-sm text-gray-500">
          Powered by{" "}
          <a
            href="https://datadr.io"
            className="text-blue-600 hover:text-blue-800 font-medium"
          >
            DataDr
          </a>
          {" "}— AI-powered data quality investigations
        </p>
      </div>
    </div>
  );
}
