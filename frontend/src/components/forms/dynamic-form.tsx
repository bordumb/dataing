import { useState, useCallback, useMemo } from 'react'
import { DynamicField } from './dynamic-field'
import type { FormSchema, FieldSchema } from './field-schema'

type FormValues = Record<string, string | number | boolean>
type FormErrors = Record<string, string>

interface DynamicFormProps {
  schema: FormSchema
  initialValues?: FormValues
  onChange?: (values: FormValues) => void
  className?: string
}

function getDefaultValue(field: FieldSchema): string | number | boolean {
  if (field.defaultValue !== undefined) {
    return field.defaultValue
  }
  switch (field.type) {
    case 'number':
      return ''
    case 'checkbox':
      return false
    default:
      return ''
  }
}

function shouldShowField(field: FieldSchema, values: FormValues): boolean {
  if (!field.dependsOn) return true

  const dependentValue = values[field.dependsOn.field]
  const requiredValues = Array.isArray(field.dependsOn.value)
    ? field.dependsOn.value
    : [field.dependsOn.value]

  return requiredValues.includes(String(dependentValue))
}

export function useDynamicForm(schema: FormSchema, initialValues?: FormValues) {
  const defaultValues = useMemo(() => {
    const defaults: FormValues = {}
    for (const field of schema.fields) {
      defaults[field.name] = initialValues?.[field.name] ?? getDefaultValue(field)
    }
    return defaults
  }, [schema, initialValues])

  const [values, setValues] = useState<FormValues>(defaultValues)
  const [errors, setErrors] = useState<FormErrors>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  const setValue = useCallback((name: string, value: string | number | boolean) => {
    setValues((prev) => ({ ...prev, [name]: value }))
    setTouched((prev) => ({ ...prev, [name]: true }))
    // Clear error when value changes
    setErrors((prev) => {
      const next = { ...prev }
      delete next[name]
      return next
    })
  }, [])

  const validate = useCallback((): boolean => {
    const newErrors: FormErrors = {}

    for (const field of schema.fields) {
      if (!shouldShowField(field, values)) continue

      const value = values[field.name]

      if (field.required) {
        if (value === '' || value === undefined || value === null) {
          newErrors[field.name] = `${field.label} is required`
        }
      }

      if (field.pattern && typeof value === 'string' && value) {
        const regex = new RegExp(field.pattern)
        if (!regex.test(value)) {
          newErrors[field.name] = `${field.label} format is invalid`
        }
      }

      if (field.type === 'number' && typeof value === 'number') {
        if (field.min !== undefined && value < field.min) {
          newErrors[field.name] = `${field.label} must be at least ${field.min}`
        }
        if (field.max !== undefined && value > field.max) {
          newErrors[field.name] = `${field.label} must be at most ${field.max}`
        }
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }, [schema, values])

  const reset = useCallback(() => {
    setValues(defaultValues)
    setErrors({})
    setTouched({})
  }, [defaultValues])

  const getConfigObject = useCallback((): Record<string, unknown> => {
    const config: Record<string, unknown> = {}
    for (const field of schema.fields) {
      if (!shouldShowField(field, values)) continue
      const value = values[field.name]
      // Only include non-empty values
      if (value !== '' && value !== undefined && value !== null) {
        config[field.name] = value
      }
    }
    return config
  }, [schema, values])

  return {
    values,
    errors,
    touched,
    setValue,
    validate,
    reset,
    getConfigObject,
    isValid: Object.keys(errors).length === 0,
  }
}

export function DynamicForm({ schema, initialValues, onChange, className }: DynamicFormProps) {
  const { values, errors, setValue } = useDynamicForm(schema, initialValues)

  const handleChange = (name: string, value: string | number | boolean) => {
    setValue(name, value)
    onChange?.({ ...values, [name]: value })
  }

  const visibleFields = schema.fields.filter((field) => shouldShowField(field, values))

  return (
    <div className={className}>
      <div className="space-y-4">
        {visibleFields.map((field) => (
          <DynamicField
            key={field.name}
            field={field}
            value={values[field.name]}
            onChange={handleChange}
            error={errors[field.name]}
          />
        ))}
      </div>
    </div>
  )
}

// Re-export for convenience
export { type FormSchema, type FieldSchema, getSchemaForType } from './field-schema'
