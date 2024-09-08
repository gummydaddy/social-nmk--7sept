// WebRTCComponent.js
import React, { useEffect, useRef, useState } from 'react';

const WebRTCComponent = ({ roomName }) => {
    const localVideoRef = useRef();
    const remoteVideoRef = useRef();
    const [pc, setPc] = useState(null);
    const [socket, setSocket] = useState(null);

    useEffect(() => {
        const socket = new WebSocket(`wss://localhost:8000/ws/call/${roomName}/`);
        setSocket(socket);

        const pc = new RTCPeerConnection({
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' }
            ]
        });

        pc.onicecandidate = event => {
            if (event.candidate) {
                socket.send(JSON.stringify({ type: 'candidate', candidate: event.candidate }));
            }
        };

        pc.ontrack = event => {
            remoteVideoRef.current.srcObject = event.streams[0];
        };

        navigator.mediaDevices.getUserMedia({ video: true, audio: true })
            .then(stream => {
                localVideoRef.current.srcObject = stream;
                stream.getTracks().forEach(track => pc.addTrack(track, stream));
            });

        socket.onmessage = event => {
            const data = JSON.parse(event.data);
            switch (data.type) {
                case 'offer':
                    pc.setRemoteDescription(new RTCSessionDescription(data.offer));
                    pc.createAnswer()
                        .then(answer => pc.setLocalDescription(answer))
                        .then(() => {
                            socket.send(JSON.stringify({ type: 'answer', answer: pc.localDescription }));
                        });
                    break;
                case 'answer':
                    pc.setRemoteDescription(new RTCSessionDescription(data.answer));
                    break;
                case 'candidate':
                    pc.addIceCandidate(new RTCIceCandidate(data.candidate));
                    break;
                default:
                    break;
            }
        };

        setPc(pc);

        return () => {
            pc.close();
            socket.close();
        };
    }, [roomName]);

    const startCall = () => {
        pc.createOffer()
            .then(offer => pc.setLocalDescription(offer))
            .then(() => {
                socket.send(JSON.stringify({ type: 'offer', offer: pc.localDescription }));
            });
    };

    return (
        <div>
            <video ref={localVideoRef} autoPlay muted></video>
            <video ref={remoteVideoRef} autoPlay></video>
            <button onClick={startCall}>Start Call</button>
        </div>
    );
};

export default WebRTCComponent;
