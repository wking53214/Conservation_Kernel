"""Append-only artifact and verification ledger."""

from __future__ import annotations

from collections.abc import Callable

from .errors import LedgerError, RootAdmissionError
from .events import TransformationRecord
from .model import Artifact
from .result import VerificationResult


class ConservationLedger:
    """Small in-memory ledger for the first experiment.

    It is append-only at the public API: artifacts and accepted transformation
    records cannot be replaced. Rejected attempts are retained as reports so a
    failed transition is visible rather than disappearing.
    """

    def __init__(self, *, root_guard: Callable[[Artifact], bool] | None = None) -> None:
        """`root_guard`, if given, is asked before any initial artifact is added, and the artifact is added only
        if it answers True. It is the caller's own permission check (the kernel imports nothing to supply one); a
        guard that raises or answers anything but True refuses. If it has `commit` and `abort` methods it is told
        which happened after a yes: `commit()` once the root is in, `abort()` if adding it raised. Rebuilding a ledger from a snapshot does not ask it."""
        self._root_guard = root_guard
        self._artifacts: dict[str, Artifact] = {}
        self._transformations: dict[str, TransformationRecord] = {}
        self._reports: list[VerificationResult] = []
        # When the kernel admitted each root, and when it verified each committed transformation, by its clock. A
        # restore re-judges each as of its moment. Set only by add_initial / commit (or once, on first reload, for
        # history written before times existed), never from a later attempt that the ledger refused.
        self._admitted_at: dict[str, str] = {}
        self._verified_at: dict[str, str] = {}

    @property
    def root_guard(self) -> Callable[[Artifact], bool] | None:
        """The guard this ledger was built with, for a caller deciding whether it is one they trust. None if there is none."""
        return self._root_guard

    @property
    def has_root_guard(self) -> bool:
        """Whether adding an initial artifact depends on a guard. Says nothing about what the guard will answer."""
        return self._root_guard is not None

    def add_initial(self, artifact: Artifact, *, admitted_at: str | None = None) -> None:
        if artifact.parent_artifact_ids:
            raise LedgerError("an initial artifact cannot already have parents")
        if artifact.artifact_id in self._artifacts:
            raise LedgerError(f"duplicate artifact ID {artifact.artifact_id}")
        if self._root_guard is not None:
            try:
                permitted = self._root_guard(artifact) is True
            except Exception:  # a guard that cannot answer never permits
                permitted = False
            if not permitted:
                raise RootAdmissionError("root refused: the root guard did not authorize this artifact")
        try:
            self._add_artifact(artifact)
            if admitted_at is not None:
                self._admitted_at[artifact.artifact_id] = admitted_at
        except Exception:
            self._tell_root_guard("abort")  # a yes was given and nothing was written: the guard may give it back
            raise
        self._tell_root_guard("commit")

    def _tell_root_guard(self, how: str) -> None:
        """Tell a root guard that offers `commit` and `abort` how the write it permitted ended. A guard with neither is
        left alone, and one that raises while being told does not hide the write or its failure."""
        settle = getattr(self._root_guard, how, None)
        if callable(settle):
            try:
                settle()
            except Exception:  # noqa: BLE001 - the write has happened or failed; the guard's own trouble stays its own
                pass

    def admitted_at(self, artifact_id: str) -> str | None:
        """When the kernel admitted this root, or None if it was added without a time (or before stamps)."""
        return self._admitted_at.get(artifact_id)

    def verified_at(self, transformation_id: str) -> str | None:
        """When the committed verification of this transformation was made, or None if it carries no time.

        Taken from the commit itself, not from the reports: a later attempt that re-used the id was verified and
        reported but refused by the ledger, and must not move this transformation's time."""
        return self._verified_at.get(transformation_id)

    def record_times(self, *, admitted: dict[str, str] | None = None, verified: dict[str, str] | None = None) -> None:
        """Give a time to history that has none (roots or committed transformations written before times existed,
        or straight to the ledger). A time already recorded is never replaced."""
        for artifact_id, moment in (admitted or {}).items():
            if artifact_id not in self._artifacts:
                raise LedgerError(f"no artifact {artifact_id} to record a time for")
            self._admitted_at.setdefault(artifact_id, moment)
        for transformation_id, moment in (verified or {}).items():
            if transformation_id not in self._transformations:
                raise LedgerError(f"no transformation {transformation_id} to record a time for")
            self._verified_at.setdefault(transformation_id, moment)

    def _add_artifact(self, artifact: Artifact) -> None:
        if artifact.artifact_id in self._artifacts:
            raise LedgerError(f"duplicate artifact ID {artifact.artifact_id}")
        self._artifacts[artifact.artifact_id] = artifact

    def commit(self, output: Artifact, record: TransformationRecord, result: VerificationResult) -> None:
        if not result.accepted:
            raise LedgerError("a rejected or unverifiable result cannot be committed")
        if result.output_artifact_id != output.artifact_id:
            raise LedgerError("result and output IDs do not match")
        if output.artifact_id in self._artifacts:
            raise LedgerError(f"duplicate artifact ID {output.artifact_id}")
        if not output.parent_artifact_ids:
            # An output with no parents is a root. Roots enter through `add_initial`, which asks the root guard;
            # letting one in here would walk around that guard with a result the caller wrote by hand.
            raise LedgerError(f"artifact {output.artifact_id} has no parents, so it is a root; "
                              "roots are added with add_initial, which asks the root guard")
        for parent in output.parent_artifact_ids:
            if parent not in self._artifacts:
                raise LedgerError(f"parent artifact {parent} is not in the ledger")
        if record.transformation_id in self._transformations:
            raise LedgerError(f"duplicate transformation ID {record.transformation_id}")
        self._add_artifact(output)
        self._transformations[record.transformation_id] = record
        self._reports.append(result)
        if result.verified_at is not None:
            self._verified_at[record.transformation_id] = result.verified_at

    def record_rejection(self, result: VerificationResult) -> None:
        self._reports.append(result)

    def artifact(self, artifact_id: str) -> Artifact:
        return self._artifacts[artifact_id]

    def artifacts(self) -> tuple[Artifact, ...]:
        return tuple(self._artifacts.values())

    def transformations(self) -> tuple[TransformationRecord, ...]:
        return tuple(self._transformations.values())

    def reports(self) -> tuple[VerificationResult, ...]:
        return tuple(self._reports)

    def transformation_for_output(self, artifact_id: str) -> TransformationRecord | None:
        return next((item for item in self._transformations.values() if item.output_artifact_id == artifact_id), None)

    def snapshot(self) -> dict:
        return {
            "artifacts": [item.to_dict() for item in self._artifacts.values()],
            "transformations": [item.to_dict() for item in self._transformations.values()],
            "reports": [item.to_dict() for item in self._reports],
            # Present only when there is something to record, so an unstamped ledger keeps its old shape.
            **({"root_admitted_at": dict(self._admitted_at)} if self._admitted_at else {}),
            **({"transformation_verified_at": dict(self._verified_at)} if self._verified_at else {}),
        }

    @classmethod
    def restore(cls, snapshot: dict, *, root_guard: Callable[[Artifact], bool] | None = None) -> "ConservationLedger":
        """A ledger rebuilt from `snapshot()`. Every artifact's digests are
        recomputed and compared on the way in (Artifact.from_dict), so a
        snapshot whose bytes were altered is refused; whether the lineage in
        it was ever verified is the kernel's question, see
        ConservationKernel.from_snapshot. The roots in the snapshot are not put to
        `root_guard` (they were guarded, or not, when first registered); it guards roots added after."""
        ledger = cls(root_guard=root_guard)
        for item in snapshot.get("artifacts", []):
            artifact = Artifact.from_dict(item)
            ledger._add_artifact(artifact)
        for item in snapshot.get("transformations", []):
            record = TransformationRecord.from_dict(item)
            if record.output_artifact_id not in ledger._artifacts:
                raise LedgerError(f"snapshot transformation {record.transformation_id} names an output not in the snapshot")
            ledger._transformations[record.transformation_id] = record
        for item in snapshot.get("reports", []):
            ledger._reports.append(VerificationResult.from_dict(item))
        for artifact_id, admitted_at in snapshot.get("root_admitted_at", {}).items():
            if artifact_id not in ledger._artifacts:
                raise LedgerError(f"snapshot records an admission time for {artifact_id}, which is not in the snapshot")
            ledger._admitted_at[artifact_id] = admitted_at
        for transformation_id, verified_at in snapshot.get("transformation_verified_at", {}).items():
            if transformation_id not in ledger._transformations:
                raise LedgerError(f"snapshot records a verification time for {transformation_id}, "
                                  "which is not in the snapshot")
            ledger._verified_at[transformation_id] = verified_at
        return ledger
