import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

export default function NotFound() {
  const { t } = useTranslation('common')
  return (
    <div className="flex min-h-screen items-center justify-center bg-steel-900">
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-bold text-primary-400">{t('notFound.title')}</h1>
        <p className="text-steel-300">{t('notFound.message')}</p>
        <Link
          to="/"
          className="text-sm text-primary-400 hover:text-primary-300 underline"
        >
          {t('notFound.backHome')}
        </Link>
      </div>
    </div>
  )
}
