from app.persistence.database import SessionLocal
from app.retrieval.ingestion import PolicyIngestionService


def main() -> None:
    with SessionLocal() as session:
        report = PolicyIngestionService(session).ingest_all()
    print(f"Ingested: {report.ingested}; quarantined: {report.quarantined}")
    for entry in report.entries:
        print(f"{entry['status']}: {entry['path']} ({entry['detail']})")


if __name__ == "__main__":
    main()
