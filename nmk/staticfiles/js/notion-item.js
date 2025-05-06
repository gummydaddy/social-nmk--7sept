// static/js/notion-item.js
Vue.component('notion-item', {
    props: ['notion'],
    template: `
        <div class="notion-item">
            <div class="notion-content">
                <a :href="'/user_profile/profile/' + notion.user.id">
                    {{ notion.user.username }}
                </a>
                <p>{{ notion.content }}</p>
                <p v-if="notion.custom_group">Group: {{ notion.custom_group.name }}</p>
                <p>{{ notion.created_at }}</p>
            </div>
            <div class="actions">
                <a href="#" @click.prevent="likeNotion" :class="{ 'liked': notion.is_liked }">
                    {{ notion.is_liked ? '❤️' : '♡' }}
                </a>
                <span class="like-count">{{ notion.like_count }}</span> likes
                <a :href="'/notion/notion_detail/' + notion.id">Comment</a>
            </div>
        </div>
    `,
    methods: {
        likeNotion() {
            this.$emit('like', this.notion.id);
        }
    }
});
