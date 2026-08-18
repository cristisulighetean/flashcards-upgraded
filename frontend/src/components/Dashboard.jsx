import React, { useEffect, useState } from 'react';
import { listFlashcards, listPendingFlashcards } from '../api';
import { BookOpen, Layers, Zap, ShieldCheck, ChevronDown, ChevronRight, FileText } from 'lucide-react';

const Dashboard = ({ onStartReview, onReviewNew, onBrowseCard }) => {
  const [cards, setCards] = useState([]);
  const [stats, setStats] = useState({ inventory: 0, mastery: 0, focus: 0 });
  const [pendingCount, setPendingCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState(new Set());

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setIsLoading(true);
        // Document-generated cards only: this whole page — stats, "Study
        // Collection", and the Library below — is the qa-card home now that
        // vocabulary has its own page with its own stats and study buttons.
        // Mixing the two here would make the Inventory tile disagree with
        // what the Library section actually shows.
        const all = await listFlashcards(100, 'qa');
        const pending = await listPendingFlashcards('qa');

        setCards(all.flashcards || []);

        // Use global stats from API metadata
        setStats({
          inventory: all.total_inventory || 0,
          mastery: all.avg_mastery || 0,
          focus: all.needs_focus_count || 0
        });

        setPendingCount(pending.total || 0);
      } catch (err) {
        console.error('Failed to load flashcards', err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchStats();
  }, []);

  const toggleGroup = (filename) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  };

  // `cards` is already qa-only from the fetch above; this filter is a cheap
  // guard against a card with no document_filename (defensive, not expected).
  const libraryCards = cards.filter((card) => card.document_filename);

  const groupedCards = libraryCards.reduce((acc, card) => {
    const key = card.document_filename;
    if (!acc[key]) acc[key] = [];
    acc[key].push(card);
    return acc;
  }, {});

  const totalCards = libraryCards.length;

  if (isLoading) {
    return <div className="loader-container" style={{marginTop: '100px'}}><div className="spinner"></div></div>;
  }

  return (
    <div>
      <div className="dashboard-header">
        <div>
          <h1 className="text-gradient">Your Knowledge Base</h1>
          <p className="text-secondary">Continuous adaptive learning driven by your feedback.</p>
        </div>

        <div className="dashboard-actions">
          {pendingCount > 0 && (
            <button
              className="btn btn-secondary"
              onClick={onReviewNew}
              style={{ borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)' }}
            >
              <ShieldCheck size={18} /> Quality Control ({pendingCount})
            </button>
          )}

          <button
            className="btn btn-primary"
            onClick={onStartReview}
            disabled={stats.inventory === 0}
          >
            <BookOpen size={18} /> Study Collection
          </button>
        </div>
      </div>

      <div className="dashboard-stats">
        <div className="stat-card glass-panel">
          <Layers size={24} color="var(--accent-purple)" />
          <div className="stat-value">{stats.inventory}</div>
          <div className="stat-label">Inventory</div>
        </div>
        <div className="stat-card glass-panel">
          <Zap size={24} color="#ffd32a" />
          <div className="stat-value">{stats.focus}</div>
          <div className="stat-label">Needs Focus</div>
        </div>
        <div className="stat-card glass-panel">
          <BookOpen size={24} color="var(--accent-cyan)" />
          <div className="stat-value">{stats.mastery === 0 ? '-' : stats.mastery}</div>
          <div className="stat-label">Avg Mastery</div>
        </div>
      </div>

      <div className="library-header">
        <h3 style={{ fontFamily: 'Outfit' }}>Library</h3>
        {totalCards > 0 && (
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Categorized by file · {totalCards} cards visible
          </span>
        )}
      </div>

      {Object.keys(groupedCards).length === 0 ? (
        <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-secondary)' }}>
          <p>You haven't generated any flashcards yet.</p>
        </div>
      ) : (
        <div className="library-accordion">
          {Object.entries(groupedCards).map(([filename, groupCards]) => {
            const isExpanded = expandedGroups.has(filename);
            return (
              <div key={filename} className="category-group" style={{ marginBottom: '1rem' }}>
                <div 
                  className={`category-header glass-panel ${isExpanded ? 'active' : ''}`}
                  onClick={() => toggleGroup(filename)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '1rem 1.5rem',
                    cursor: 'pointer',
                    borderRadius: '12px',
                    transition: 'all 0.3s ease',
                    border: '1px solid rgba(255,255,255,0.05)'
                  }}
                >
                  <div style={{ marginRight: '1rem', display: 'flex' }}>
                    {isExpanded ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
                  </div>
                  <FileText size={18} style={{ marginRight: '0.75rem', color: 'var(--accent-cyan)', opacity: 0.8 }} />
                  <span style={{ fontWeight: '600', flex: 1 }}>{filename}</span>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', opacity: 0.7 }}>
                    {groupCards.length} cards
                  </span>
                </div>
                
                {isExpanded && (
                  <div className="category-content" style={{ paddingTop: '1rem', paddingLeft: '1rem' }}>
                    <div className="cards-grid">
                      {groupCards.map((card) => {
                        // Index within the library, so browsing steps
                        // through file-backed cards only.
                        const cardIndex = libraryCards.findIndex(c => c.id === card.id);
                        return (
                          <div
                            key={card.id}
                            className="mini-card glass-panel"
                            onClick={(e) => {
                              e.stopPropagation();
                              onBrowseCard(libraryCards, cardIndex);
                            }}
                            style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column' }}
                          >
                            <div className="mini-card-q" style={{ fontWeight: '600', marginBottom: '8px' }}>
                              {card.question}
                            </div>
                            <div className="mini-card-meta" style={{ marginTop: 'auto', paddingTop: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                Mastery: {card.ease_factor.toFixed(1)}
                              </span>
                              {card.priority_score > 3.0 && (
                                <span style={{ fontSize: '0.7rem', color: '#ffd32a', fontWeight: 'bold' }}>
                                  <Zap size={10} style={{ verticalAlign: 'middle', marginRight: '2px' }} />
                                  Focus
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Dashboard;
