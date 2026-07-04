
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

export class CargoAIAssistant extends Component {
    setup() {
        try {
            this.state = useState({
                isOpen: false,
                messages: [{ role: "ai", text: "Hello! I am your Cargo AI. You can type or use your voice to ask me to generate reports or fill out a new invoice form." }],
                inputText: "",
                isListening: false,
                isLoading: false
            });
            
            this.action = useService("action");
            
            // Speech Recognition variables
            this.mediaRecorder = null;
            this.audioChunks = [];
        } catch (e) {
            console.error("Cargo AI setup failed:", e);
        }
    }

    toggleChat() {
        this.state.isOpen = !this.state.isOpen;
    }

    async toggleListen() {
        if (this.state.isListening) {
            // Stop recording
            if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
                this.mediaRecorder.stop();
                this.state.isListening = false;
            }
        } else {
            // Start recording
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                this.mediaRecorder = new MediaRecorder(stream);
                this.audioChunks = [];

                this.mediaRecorder.ondataavailable = (event) => {
                    if (event.data.size > 0) {
                        this.audioChunks.push(event.data);
                    }
                };

                this.mediaRecorder.onstop = async () => {
                    const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
                    // Convert blob to base64
                    const reader = new FileReader();
                    reader.readAsDataURL(audioBlob);
                    reader.onloadend = () => {
                        const base64data = reader.result.split(',')[1];
                        this.sendAudioToServer(base64data);
                    };
                    
                    // Stop all tracks to release microphone
                    stream.getTracks().forEach(track => track.stop());
                };

                this.mediaRecorder.start();
                this.state.isListening = true;
            } catch (err) {
                console.error("Microphone access denied or error:", err);
                alert("Could not access microphone. Please ensure microphone permissions are granted.");
            }
        }
    }

    async sendAudioToServer(base64Audio) {
        this.state.isLoading = true;
        this.state.messages.push({ role: "user", text: "🎙️ (Audio Recording)" });
        try {
            const response = await rpc("/cargo/ai/speech_to_text", { audio_data: base64Audio });
            if (response.error) {
                this.state.messages.push({ role: "ai", text: "Error: " + response.error });
            } else if (response.text) {
                // Now we have the transcribed text, send it to the AI query logic!
                this.state.inputText = response.text;
                await this.sendMessage();
            }
        } catch (error) {
            this.state.messages.push({ role: "ai", text: "Sorry, I encountered an error processing audio." });
            console.error(error);
        } finally {
            this.state.isLoading = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            this.sendMessage();
        }
    }

    async sendMessage() {
        if (!this.state.inputText.trim()) return;
        
        const query = this.state.inputText;
        this.state.messages.push({ role: "user", text: query });
        this.state.inputText = "";
        this.state.isLoading = true;
        
        try {
            const response = await rpc("/cargo/ai/query", { query: query });
            
            if (response.error) {
                this.state.messages.push({ role: "ai", text: "Error: " + response.error });
            } else if (response.action_type === 'chat_response') {
                this.state.messages.push({ role: "ai", text: response.message });
            } else if (response.action_type === 'ir.actions.act_window') {
                this.state.messages.push({ role: "ai", text: "I have prepared the form for you based on what you said. Opening now!" });
                this.action.doAction(response.action);
            } else if (response.action_type === 'ir.actions.report') {
                this.state.messages.push({ role: "ai", text: "Here is the report you requested! It should start downloading automatically." });
                this.action.doAction(response.action);
            } else if (response.action_type === 'ir.actions.client') {
                this.state.messages.push({ role: "ai", text: "Email sent successfully!" });
                this.action.doAction(response.action);
            } else {
                this.state.messages.push({ role: "ai", text: "Action executed successfully." });
            }
        } catch (error) {
            this.state.messages.push({ role: "ai", text: "JS Error: " + (error.message || error.toString()) });
            console.error(error);
        } finally {
            this.state.isLoading = false;
        }
    }
}

CargoAIAssistant.template = "cargo_manual_invoicing.CargoAIAssistant";

registry.category("systray").add("CargoAIAssistant", {
    Component: CargoAIAssistant,
}, { sequence: 1 });
