{{/*
Common labels applied to all resources.
These enable kubectl filtering and Helm management.
*/}}
{{- define "url-shortener.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — used in Service and Deployment selectors.
Must be STABLE — changing these breaks existing deployments.
*/}}
{{- define "url-shortener.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Resource name helpers */}}
{{- define "url-shortener.appName" -}}
{{ .Release.Name }}-app
{{- end }}

{{- define "url-shortener.redisName" -}}
{{ .Release.Name }}-redis
{{- end }}
