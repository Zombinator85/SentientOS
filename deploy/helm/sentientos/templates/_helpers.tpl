{{- define "sentientos.name" -}}
sentientos
{{- end -}}

{{- define "sentientos.fullname" -}}
{{ include "sentientos.name" . }}-{{ .Release.Name }}
{{- end -}}
