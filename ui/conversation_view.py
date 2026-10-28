"""
The voice conversation screen (used by Voice Practice and Interview Practice).

One turn, step by step
----------------------
1. You record with the microphone widget (your browser records; nothing
   starts automatically).
2. ``_process_audio`` decodes the WAV, checks its quality, and runs Whisper.
3. The text goes to ``ConversationEngine`` which asks Ollama for a reply.
4. The reply is turned into speech (Piper or Windows voice).
5. The page re-runs, shows the reply and plays it once.
6. If feedback is due (see feedback_engine), grammar is checked while the
   reply is playing.

Duplicate protection: each recording is fingerprinted (SHA-1). Streamlit
re-runs the script on every click, so without this the same recording
could be processed twice. After processing, the microphone widget is reset by
changing its key.
"""

from __future__ import annotations

import hashlib
import logging

import streamlit as st

from audio.audio_utils import AudioError, analyze_quality, decode_wav
from config.prompts import MODES
from core.conversation_engine import ConversationEngine, Message
from core.feedback_engine import compute_session_stats, generate_session_feedback, turns_due_for_feedback
from core.fluency_analyzer import analyze_fluency
from core.grammar_analyzer import GrammarAnalyzer, GrammarFeedback
from core.llm_client import LLMError
from core.performance_monitor import TurnTiming, process_memory_mb, timed
from core.speech_recognition import SpeechRecognitionError
from core.speech_synthesis import SpeechSynthesisError
from database import repository
from ui import components, state

logger = logging.getLogger(__name__)


class ConversationView:
    def __init__(self, key: str, modes: list[str]):
        self.k = key            # session_state prefix, e.g. "voice" or "interview"
        self.modes = modes
        ss = st.session_state
        ss.setdefault(f"{key}_engine", None)
        ss.setdefault(f"{key}_mic", 0)
        ss.setdefault(f"{key}_seen", set())
        ss.setdefault(f"{key}_feedback", {})       # message index -> (GrammarFeedback dict, db id)
        ss.setdefault(f"{key}_checked", 0)         # how many user answers were checked
        ss.setdefault(f"{key}_reply_audio", None)  # (message index, wav bytes)
        ss.setdefault(f"{key}_autoplay", False)
        ss.setdefault(f"{key}_extra_audio", None)  # "Hear it" audio
        ss.setdefault(f"{key}_session_fb", None)
        ss.setdefault(f"{key}_error", None)

    # ----------------------------------------------------------- properties
    @property
    def engine(self) -> ConversationEngine | None:
        return st.session_state[f"{self.k}_engine"]

    def _get(self, name):
        return st.session_state[f"{self.k}_{name}"]

    def _set(self, name, value):
        st.session_state[f"{self.k}_{name}"] = value

    # ---------------------------------------------------------------- render
    def render(self) -> None:
        settings = state.get_settings()
        profile = state.get_profile()
        if self.engine is None:
            self._render_setup(settings, profile)
        else:
            self._render_session(settings, profile)

    def _render_setup(self, settings, profile) -> None:
        errors, warnings = components.readiness_messages(settings)
        preset = st.session_state.pop(f"{self.k}_preset_mode", None)
        default_mode = preset if preset in self.modes else self.modes[0]
        if len(self.modes) > 1:
            mode = st.selectbox("Practice type", self.modes, index=self.modes.index(default_mode),
                                format_func=lambda m: MODES[m]["label"], key=f"{self.k}_mode_pick")
        else:
            mode = self.modes[0]
        scenarios = MODES[mode]["scenarios"]
        scenario = st.selectbox("Scenario" if mode != "daily" else "Topic", scenarios,
                                key=f"{self.k}_scenario_pick_{mode}")
        if mode == "free":
            scenario = st.text_input("Topic (optional)", max_chars=80, key=f"{self.k}_free_topic") or scenario

        for e in errors:
            st.error(e, icon=":material/error:")
        for w in warnings:
            st.warning(w, icon=":material/warning:")
        if errors:
            st.caption("Fix the problem above, then reload this page. See docs/TROUBLESHOOTING.md for help.")

        freq_label = {"every_turn": "after every answer", "every_3_turns": "after every 3 answers",
                      "end_of_session": "at the end", "on_request": "only when you ask"}
        st.caption(f"Feedback: {freq_label.get(profile['feedback_frequency'])} · Level: {profile['proficiency']} "
                   f"· {profile['variety']} English · History {'on' if settings.save_history else 'off'} "
                   "(change in Settings)")
        if st.button("Start session", type="primary", disabled=bool(errors), icon=":material/play_arrow:"):
            engine = ConversationEngine(
                state.get_llm(settings), mode=mode, scenario=scenario.strip()[:80],
                proficiency=profile["proficiency"], variety=profile["variety"],
                context_turns=settings.context_turns, max_reply_tokens=settings.max_reply_tokens,
                save_history=settings.save_history)
            opening = engine.start()
            self._reset_session_state()
            self._set("engine", engine)
            self._speak_reply(settings, opening, len(engine.messages) - 1)
            st.rerun()

    def _reset_session_state(self) -> None:
        for name, value in (("feedback", {}), ("checked", 0), ("reply_audio", None), ("autoplay", False),
                            ("extra_audio", None), ("session_fb", None), ("error", None), ("seen", set())):
            self._set(name, value)

    def _render_session(self, settings, profile) -> None:
        engine = self.engine
        mode_info = MODES[engine.mode]
        top = st.columns([4, 2, 1.4])
        top[0].markdown(f"#### {mode_info['label']} · {engine.scenario}")
        if not engine.ended:
            if top[1].button("End session & get feedback", type="primary", icon=":material/flag:"):
                self._end_session(settings, profile)
                st.rerun()
        if top[2].button("New session", icon=":material/restart_alt:"):
            if not engine.ended:
                engine.end()
            self._set("engine", None)
            self._reset_session_state()
            st.rerun()

        # Conversation transcript
        for idx, msg in enumerate(engine.messages):
            self._render_message(idx, msg, settings)

        # Errors from the last turn (shown once)
        if err := self._get("error"):
            st.error(err, icon=":material/error:")
            self._set("error", None)

        if engine.ended:
            st.divider()
            st.subheader("Session feedback")
            fb = self._get("session_fb")
            if fb:
                components.render_session_feedback(fb)
            st.caption("Feedback on individual answers is shown under each answer above. "
                       "Press 'New session' to practise again.")
            return

        # Grammar checks that are due (runs while the reply audio plays)
        self._run_due_feedback(settings, profile)

        self._render_input(settings, profile)
        # The reply has been played once; later re-runs must not replay it.
        self._set("autoplay", False)

    def _render_message(self, idx: int, msg: Message, settings) -> None:
        avatar = ":material/person:" if msg.role == "user" else ":material/school:"
        with st.chat_message(msg.role, avatar=avatar):
            st.markdown(msg.text)
            if msg.role == "user":
                if msg.metrics.get("speaking_seconds") and msg.input_type == "voice":
                    with st.expander("Speaking metrics", icon=":material/speed:"):
                        components.render_fluency(msg.metrics)
                if idx in self._get("feedback"):
                    with st.expander("Feedback", expanded=idx == self._last_user_index(),
                                     icon=":material/spellcheck:"):
                        self._render_feedback_for(idx, settings)
            else:
                timing = msg.metrics.get("timing")
                if timing:
                    parts = [f"{label} {timing[key]:.1f}s" for key, label in
                             (("asr_seconds", "speech→text"), ("llm_seconds", "AI"), ("tts_seconds", "voice"),
                              ("total_seconds", "total")) if timing.get(key) is not None]
                    st.caption(" · ".join(parts))
                reply = self._get("reply_audio")
                if reply and reply[0] == idx:
                    st.audio(reply[1], format="audio/wav", autoplay=self._get("autoplay"))
                    if st.button("Stop voice", key=f"{self.k}_stop_{idx}", icon=":material/stop:"):
                        self._set("reply_audio", None)
                        st.rerun()
                if msg.metrics.get("tts_error"):
                    st.caption(f":orange[Voice unavailable: {msg.metrics['tts_error']}]")

    def _render_feedback_for(self, idx: int, settings) -> None:
        fb_dict, fb_id = self._get("feedback")[idx]
        components.render_grammar_feedback(
            GrammarFeedback.from_dict(fb_dict), fb_id, key=f"{self.k}_fb_{idx}",
            on_hear=lambda text: self._hear(settings, text),
            on_practise=self._practise)
        extra = self._get("extra_audio")
        if extra and extra[0] == idx:
            st.audio(extra[1], format="audio/wav", autoplay=True)

    def _last_user_index(self) -> int:
        for i in range(len(self.engine.messages) - 1, -1, -1):
            if self.engine.messages[i].role == "user":
                return i
        return -1

    # ----------------------------------------------------------------- input
    def _render_input(self, settings, profile) -> None:
        st.divider()
        c1, c2 = st.columns([3, 1.2])
        with c1:
            audio = st.audio_input(
                f"Press the microphone to record your answer, press stop when finished "
                f"(max {settings.max_recording_seconds}s)",
                key=f"{self.k}_mic_{self._get('mic')}", sample_rate=16000)
        with c2:
            st.caption("While recording, the widget shows a timer and waveform. Use its trash icon "
                       "to cancel a recording.")
            if profile["feedback_frequency"] != "every_turn" and self.engine.user_messages:
                if st.button("Check my last answer", icon=":material/spellcheck:"):
                    self._check_turns(settings, profile, only_last=True)
                    st.rerun()
        with st.expander("Save a word from this conversation", icon=":material/bookmark_add:"):
            with st.form(f"{self.k}_save_word", clear_on_submit=True):
                word = st.text_input("Word or phrase", max_chars=60)
                if st.form_submit_button("Look up & save"):
                    self._save_word(settings, profile, word)
        typed = st.chat_input("...or type your answer here")

        if audio is not None:
            data = audio.getvalue()
            digest = hashlib.sha1(data).hexdigest()
            if digest not in self._get("seen"):
                self._get("seen").add(digest)
                self._process_audio(settings, data)
                self._set("mic", self._get("mic") + 1)  # new key = fresh, empty microphone widget
                st.rerun()
        if typed:
            self._process_text(settings, typed)
            st.rerun()

    # ------------------------------------------------------------ processing
    def _process_audio(self, settings, data: bytes) -> None:
        timing = TurnTiming()
        with st.status("Processing your answer...", expanded=True) as status:
            with timed() as total:
                status.write("Checking the recording...")
                try:
                    audio = decode_wav(data)
                except AudioError as exc:
                    self._set("error", str(exc))
                    status.update(label="Recording problem", state="error")
                    return
                quality = analyze_quality(audio)
                timing.audio_seconds = quality.duration_s
                if quality.duration_s < settings.min_recording_seconds:
                    self._set("error", "The recording was too short. Hold the button a little longer.")
                    status.update(label="Recording too short", state="error")
                    return
                if quality.is_silent:
                    self._set("error", " ".join(quality.warnings))
                    status.update(label="No speech detected", state="error")
                    return
                notes = list(quality.warnings)
                limit = settings.max_recording_seconds
                if quality.duration_s > limit:
                    audio = audio[: limit * 16000]
                    notes.append(f"Only the first {limit}s were used (recording limit).")

                status.write("Recognising speech (on this computer)...")
                recognizer = state.get_recognizer(settings)
                if not recognizer.is_loaded:
                    status.write("Loading the speech model for the first time - this can take a moment...")
                try:
                    with timed() as t_asr:
                        result = recognizer.transcribe(audio)
                except SpeechRecognitionError as exc:
                    self._set("error", str(exc))
                    status.update(label="Speech recognition problem", state="error")
                    return
                timing.asr_seconds = t_asr.seconds
                if recognizer.notice:
                    st.toast(recognizer.notice)
                if result.is_empty:
                    self._set("error", "I couldn't recognise any words. Please speak a little louder "
                                       "and closer to the microphone, then try again.")
                    status.update(label="No words recognised", state="error")
                    return
                status.write(f"You said: _{result.text}_")

                metrics = analyze_fluency(result.text, result.words, quality.duration_s,
                                          settings.long_pause_seconds).to_dict()
                metrics.update(audio_warnings=notes, rms_dbfs=quality.rms_dbfs,
                               asr_seconds=t_asr.seconds)
                self._respond(settings, result.text, metrics, "voice", timing, status)
            timing.total_seconds = total.seconds
            self._finish_timing(timing)

    def _process_text(self, settings, text: str) -> None:
        text = text.strip()[:2000]
        if not text:
            return
        timing = TurnTiming()
        with st.status("Thinking...", expanded=False) as status:
            with timed() as total:
                metrics = analyze_fluency(text, [], 0.0).to_dict()
                self._respond(settings, text, metrics, "text", timing, status)
            timing.total_seconds = total.seconds
            self._finish_timing(timing)

    def _respond(self, settings, text, metrics, input_type, timing: TurnTiming, status) -> None:
        engine = self.engine
        engine.add_user_message(text, metrics=metrics, input_type=input_type)
        status.write("The AI is thinking (local model)...")
        try:
            with timed() as t_llm:
                reply = engine.generate_reply()
        except LLMError as exc:
            # Remove nothing: the user's message is kept so they can retry by typing "continue".
            self._set("error", f"{exc}")
            status.update(label="AI model problem", state="error")
            return
        timing.llm_seconds = t_llm.seconds
        status.write("Creating the spoken reply...")
        timing.tts_seconds = self._speak_reply(settings, reply, len(engine.messages) - 1)
        reply.metrics["timing"] = {**timing.__dict__}
        status.update(label="Done", state="complete", expanded=False)

    def _finish_timing(self, timing: TurnTiming) -> None:
        engine = self.engine
        if engine.messages and engine.messages[-1].role == "assistant":
            engine.messages[-1].metrics["timing"] = {**timing.__dict__}
        state.get_monitor().add(timing)
        logger.info("Turn timing %s, process memory %s MB", timing, process_memory_mb())

    def _speak_reply(self, settings, msg: Message, idx: int) -> float | None:
        synth = state.get_synthesizer(settings)
        try:
            wav, seconds = synth.synthesize(msg.text)
        except SpeechSynthesisError as exc:
            msg.metrics["tts_error"] = str(exc)
            self._set("reply_audio", None)
            return None
        self._set("reply_audio", (idx, wav))
        self._set("autoplay", settings.autoplay_replies)
        return seconds

    def _hear(self, settings, text: str) -> None:
        try:
            wav, _ = state.get_synthesizer(settings).synthesize(text)
        except SpeechSynthesisError as exc:
            st.toast(f"Voice unavailable: {exc}")
            return
        self._set("extra_audio", (self._last_user_index(), wav))

    def _save_word(self, settings, profile, word: str) -> None:
        from core.vocabulary_helper import VocabularyLookupError, lookup_word

        try:
            with st.spinner("Looking up the word..."):
                entry = lookup_word(state.get_llm(settings), word, profile["variety"], profile["proficiency"])
            repository.save_word(entry.to_dict(), source="conversation")
            st.success(f"Saved **{entry.word}**: {entry.definition}")
        except ValueError as exc:
            st.warning(str(exc))
        except (VocabularyLookupError, LLMError) as exc:
            st.error(str(exc))

    def _practise(self, sentence: str) -> None:
        st.session_state["pron_custom_sentence"] = sentence
        st.switch_page("pages/pronunciation_lab.py")

    # -------------------------------------------------------------- feedback
    def _run_due_feedback(self, settings, profile) -> None:
        engine = self.engine
        n_due = turns_due_for_feedback(profile["feedback_frequency"], len(engine.user_messages),
                                       self._get("checked"))
        if not n_due:
            return
        new_indices = self._check_turns(settings, profile)
        # Show new feedback right away (without a re-run, which would stop the reply audio).
        if new_indices:
            with st.container(border=True):
                st.markdown("**Feedback on your answer**" if len(new_indices) == 1
                            else f"**Feedback on your last {len(new_indices)} answers**")
                for i in new_indices:
                    if len(new_indices) > 1:
                        st.markdown(f"_{engine.messages[i].text}_")
                    self._render_feedback_for(i, settings)

    def _check_turns(self, settings, profile, only_last: bool = False) -> list[int]:
        engine = self.engine
        analyzer = GrammarAnalyzer(state.get_llm(settings), profile["variety"], profile["proficiency"])
        user_idx = [i for i, m in enumerate(engine.messages) if m.role == "user"]
        targets = user_idx[-1:] if only_last else user_idx[self._get("checked"):]
        targets = [i for i in targets if i not in self._get("feedback")]
        if not targets:
            return []
        with st.spinner(f"Checking {len(targets)} answer(s) for feedback..."):
            for i in targets:
                msg = engine.messages[i]
                with timed() as t:
                    fb = analyzer.analyze(msg.text, context=engine.previous_assistant_text(msg))
                fb_id = None
                if engine.session_id is not None and fb.ok:
                    fb_id = repository.add_feedback("grammar", fb.to_dict(), session_id=engine.session_id,
                                                    turn_id=msg.turn_id)
                self._get("feedback")[i] = (fb.to_dict(), fb_id)
                state.get_monitor().add(TurnTiming(grammar_seconds=t.seconds))
                logger.info("Grammar check took %.2fs", t.seconds)
        if not only_last:
            self._set("checked", len(user_idx))
        return targets

    def _end_session(self, settings, profile) -> None:
        engine = self.engine
        # Pending grammar checks for "every 3" / "end of session" modes
        freq = profile["feedback_frequency"]
        if turns_due_for_feedback(freq, len(engine.user_messages), self._get("checked"), session_ending=True):
            self._check_turns(settings, profile)
        users = engine.user_messages
        stats = compute_session_stats([m.metrics for m in users], [m.input_type for m in users])
        with st.spinner("Preparing your session feedback..."):
            fb = generate_session_feedback(state.get_llm(settings), mode=engine.mode, scenario=engine.scenario,
                                           proficiency=profile["proficiency"],
                                           transcript=engine.transcript(), stats=stats)
        if engine.session_id is not None and stats.user_turns:
            repository.add_feedback("session", fb.to_dict(), session_id=engine.session_id)
        self._set("session_fb", fb.to_dict())
        engine.end()
        if engine.session_id is not None and not users:
            repository.delete_session(engine.session_id)  # don't keep empty sessions
