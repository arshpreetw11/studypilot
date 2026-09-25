import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const SELF_WEIGHTS = [1, 0.5, 0]

export default function QuizModal({ subject, topic, mastery, onClose, onError, onResult, onReplan, busy }) {
  const [quiz, setQuiz] = useState(null)
  const [answers, setAnswers] = useState({})
  const [result, setResult] = useState(null)

  useEffect(() => {
    let cancelled = false
    api
      .quiz({ subject, topic, mastery, num_questions: 5 })
      .then((q) => !cancelled && setQuiz(q))
      .catch((e) => {
        if (!cancelled) {
          onError(e.message)
          onClose()
        }
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subject, topic])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const submit = () => {
    const qs = quiz.questions
    const score =
      qs.reduce((a, q, i) => a + (q.answer_index == null ? SELF_WEIGHTS[answers[i]] ?? 0 : answers[i] === q.answer_index ? 1 : 0), 0) / qs.length
    const next = onResult(Math.round(score * 100) / 100)
    setResult({ score, next })
  }

  const allAnswered = quiz && quiz.questions.every((_, i) => answers[i] != null)

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={`Quiz on ${topic}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <span className="eyebrow">{subject} · {quiz?.source === 'ai' ? 'AI quiz' : quiz ? 'Self-check' : 'Quiz'}</span>
            <h2>{topic}</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
        </div>

        {!quiz ? (
          <div className="loading"><span className="spinner" /> Writing questions at your level…</div>
        ) : (
          <div className="modal-body">
            {quiz.questions.map((q, i) => {
              const self = q.answer_index == null
              return (
                <div key={i} className="q">
                  <p className="q-text"><b>{i + 1}.</b> {q.question}</p>
                  <div className="opts">
                    {q.options.map((o, k) => {
                      let cls = answers[i] === k ? 'picked' : ''
                      if (result && !self) {
                        if (k === q.answer_index) cls = 'correct'
                        else if (answers[i] === k) cls = 'wrong'
                      }
                      return (
                        <button key={k} className={`opt ${cls}`} disabled={!!result} onClick={() => setAnswers((a) => ({ ...a, [i]: k }))}>
                          {!self && <span className="opt-letter">{String.fromCharCode(65 + k)}</span>}
                          {o}
                        </button>
                      )
                    })}
                  </div>
                  {result && q.explanation && !self && <p className="explain small">{q.explanation}</p>}
                </div>
              )
            })}
          </div>
        )}

        {quiz && (
          <div className="modal-foot">
            {!result ? (
              <>
                <span className="muted small">{Object.keys(answers).length}/{quiz.questions.length} answered</span>
                <button className="btn primary" disabled={!allAnswered} onClick={submit}>Check answers</button>
              </>
            ) : (
              <div className="result">
                <div className={`score ${result.score >= 0.7 ? 'good' : result.score >= 0.5 ? 'mid' : 'low'}`}>{Math.round(result.score * 100)}%</div>
                <div className="result-text">
                  {result.score >= 0.85
                    ? 'Mastered! Replanning will skip extra study on this topic and keep one light review.'
                    : result.score >= 0.5
                      ? 'Solid. Replanning trims study time here and keeps the spaced reviews.'
                      : 'This one needs work. Replanning adds extra spaced reviews for it.'}
                </div>
                <div className="row gap">
                  <button className="btn ghost" onClick={onClose}>Later</button>
                  <button className="btn primary" disabled={busy} onClick={() => onReplan(result.next)}>
                    {busy ? <span className="spinner" /> : null} Update my plan
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
