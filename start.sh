#!/usr/bin/env bash
SESSION="esteira"
ROOT=~/projeto_esteira

# ==========================================
# 1. Janela Python 
# ==========================================
tmux new-session -d -s $SESSION -n python -c $ROOT

# Divide a janela (o painel da direita é criado e recebe o foco automaticamente)
tmux split-window -h -t $SESSION:python -c $ROOT

# Envia o comando do venv para o painel da direita
tmux send-keys -t $SESSION:python "source $ROOT/.venv/bin/activate" C-m

# Volta o foco para o painel da esquerda (-L) e abre o nvim
tmux select-pane -L -t $SESSION:python
tmux send-keys -t $SESSION:python 'nvim .' C-m


# ==========================================
# 2. Janela C++ 
# ==========================================
tmux new-window -t $SESSION -n cpp -c $ROOT/firmware

# Divide a janela (foco vai para a direita)
tmux split-window -h -t $SESSION:cpp -c $ROOT/firmware

# Envia o monitor serial para o painel da direita
tmux send-keys -t $SESSION:cpp 'pio device monitor' C-m

# Volta para a esquerda e abre o nvim
tmux select-pane -L -t $SESSION:cpp
tmux send-keys -t $SESSION:cpp 'nvim .' C-m


# ==========================================
# 3. Janela ROS2
# ==========================================
tmux new-window -t $SESSION -n ros2 -c $ROOT/ros2_ws

# Divide a janela (foco vai para a direita)
tmux split-window -h -t $SESSION:ros2 -c $ROOT/ros2_ws

# Carrega o ambiente ROS2 no painel da direita
tmux send-keys -t $SESSION:ros2 'source /opt/ros/humble/setup.bash' C-m

# Volta para a esquerda e abre o nvim
tmux select-pane -L -t $SESSION:ros2
tmux send-keys -t $SESSION:ros2 'nvim .' C-m


# ==========================================
# Inicia a sessão na primeira aba
# ==========================================
tmux attach -t $SESSION:python
